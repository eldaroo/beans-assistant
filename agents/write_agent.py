"""
Write/Operations Agent - Executes business operations through Python functions only.

Responsibilities:
- Execute business operations (register_sale, register_expense, register_product, add_stock)
- NO raw SQL generation
- Validate all required data is present
- Summarize business impact after execution
- NEVER use sql_db_query
"""
import re
from typing import Dict, Any
from database_config import (
    register_sale,
    register_product,
    register_product_with_stock,
    update_product_price,
    add_stock,
    register_expense,
    deactivate_product,
    cancel_sale,
    cancel_expense,
    cancel_stock_movement,
    get_last_sale,
    get_last_expense,
    get_last_stock_movement,
    get_last_operation,
    fetch_one,
)

from .state import AgentState


def create_write_agent():
    """
    Create the write operations agent.

    This agent does NOT use an LLM - it directly executes business operations
    based on the classified intent and normalized entities.

    Returns:
        Agent function that executes business operations
    """

    def execute_operation(state: AgentState) -> Dict[str, Any]:
        """
        Execute business operation based on operation_type and normalized_entities.

        Args:
            state: Current agent state with operation_type and normalized_entities

        Returns:
            Updated state with operation_result
        """
        operation_type = state.get("operation_type")
        entities = state.get("normalized_entities", {})
        missing_fields = state.get("missing_fields", [])

        # Check if we have missing required fields
        if missing_fields:
            # Disambiguation seam: "agregame N productos a stock" reads to the
            # router as ADD_STOCK with quantity=N and a missing product_ref,
            # but the user's intent is genuinely ambiguous between
            #   (a) add N units of one product (ADD_STOCK), and
            #   (b) create N distinct products (REGISTER_PRODUCT × N).
            # The generic "Me falta un dato: el producto" answers neither
            # cleanly. Detect the pattern and ask the user to pick.
            user_input = state.get("user_input") or ""
            quantity = entities.get("quantity")
            product_field_missing = any(
                f in missing_fields for f in ("product_ref", "product_id", "items")
            )
            if (
                operation_type == "ADD_STOCK"
                and quantity is not None
                and isinstance(quantity, (int, float))
                and quantity >= 2
                and product_field_missing
                and re.search(
                    r"\b" + re.escape(str(int(quantity))) + r"\s+(productos|articulos|artículos|items|cosas)\b",
                    user_input,
                    flags=re.IGNORECASE,
                )
            ):
                disambiguation = (
                    f"Tu mensaje es ambiguo. ¿Qué querés hacer?\n\n"
                    f"• Agregar *{int(quantity)} unidades* de un producto existente "
                    f"(decime el nombre)\n"
                    f"• Crear *{int(quantity)} productos distintos* "
                    f"(pasame los nombres separados por coma)"
                )
                return {
                    "operation_result": None,
                    "error": disambiguation,
                    "final_answer": disambiguation,
                    "messages": [{
                        "role": "assistant",
                        "content": "[Write Agent] ADD_STOCK / REGISTER_PRODUCT ambiguity"
                    }]
                }

            # Translate technical field names to user-friendly Spanish
            field_translations = {
                "unit_price": "el precio de venta",
                "unit_price_cents": "el precio de venta",
                "unit_cost": "el costo de producción",
                "unit_cost_cents": "el costo de producción",
                "name": "el nombre del producto",
                "amount": "el monto",
                "amount_cents": "el monto",
                "description": "la descripción",
                "product_ref": "el producto",
                "product_id": "el producto",
                "quantity": "la cantidad",
                "items": "los productos",
            }

            friendly_missing = [field_translations.get(field, field) for field in missing_fields]

            if len(friendly_missing) == 1:
                error_msg = f"Me falta un dato: *{friendly_missing[0]}*\n\n¿Me lo podés decir?"
            else:
                fields_list = "\n• ".join(friendly_missing)
                error_msg = f"Me faltan algunos datos:\n• {fields_list}\n\n¿Me los podés decir?"

            return {
                "operation_result": None,
                "error": error_msg,
                "final_answer": error_msg,
                "messages": [{
                    "role": "assistant",
                    "content": f"[Write Agent] Missing fields"
                }]
            }

        try:
            result = None
            operation_summary = ""

            if operation_type == "REGISTER_SALE":
                # Prepare sale data
                items = entities.get("items", [])
                status = entities.get("status", "PAID")

                if not items:
                    raise ValueError("No se especificaron artículos para la venta")

                # CRITICAL SAFETY CHECK: Verify NO items have resolution errors
                for item in items:
                    if "resolution_error" in item:
                        raise ValueError(item["resolution_error"])

                # Block sale if any item refers to a product with NULL price.
                # If the user provided an inline override (item["unit_price_cents"]),
                # the sale proceeds with that override and the catalog price stays
                # untouched.
                for item in items:
                    if item.get("unit_price_cents") is not None:
                        continue
                    product_id = item.get("product_id")
                    if product_id is None:
                        continue
                    row = fetch_one(
                        "SELECT name, unit_price_cents FROM products WHERE id = %s",
                        (product_id,),
                    )
                    if row is not None and row["unit_price_cents"] is None:
                        product_name = row["name"]
                        block_msg = (
                            f"Necesito el precio de venta de *{product_name}* antes "
                            f"de cobrar. A cuanto la vendes?"
                        )
                        return {
                            "operation_result": None,
                            "error": block_msg,
                            "final_answer": block_msg,
                            "messages": [{
                                "role": "assistant",
                                "content": (
                                    f"[Write Agent] REGISTER_SALE blocked: "
                                    f"product {product_id} has NULL price"
                                )
                            }]
                        }

                sale_data = {
                    "items": items,
                    "status": status
                }

                result = register_sale(sale_data)

                # Build friendly message
                items_text = []
                for item in items:
                    product_name = item.get("resolved_name", "Producto")
                    qty = item.get("quantity", 0)
                    items_text.append(f"{qty} {product_name}")

                operation_summary = f"*✅ Venta registrada!*\n\n"
                operation_summary += "• " + "\n• ".join(items_text)
                operation_summary += f"\n• Total: *${result['total_usd']:.2f}*"

                if result.get('revenue_usd'):
                    operation_summary += f"\n\n_Ventas totales: ${result['revenue_usd']:.2f}_"
                if result.get('profit_usd'):
                    profit = result['profit_usd']
                    if profit >= 0:
                        operation_summary += f"\n_Ganancia acumulada: ${profit:.2f}_"
                    else:
                        operation_summary += f"\n_Pérdida acumulada: ${abs(profit):.2f}_"

            elif operation_type == "REGISTER_EXPENSE":
                # Prepare expense data
                amount_cents = entities.get("amount_cents")
                description = entities.get("description", "Gasto")
                category = entities.get("category", "GENERAL")
                expense_date = entities.get("date")

                if amount_cents is None:
                    raise ValueError("Se requiere el monto para el gasto")

                expense_data = {
                    "amount_cents": amount_cents,
                    "description": description,
                    "category": category,
                }
                if expense_date:
                    expense_data["expense_date"] = expense_date

                result = register_expense(expense_data)

                operation_summary = f"*💸 Gasto registrado!*\n\n"
                operation_summary += f"• {description}\n"
                operation_summary += f"• Monto: *${result['amount_usd']:.2f}*"

                if result.get('profit_usd') is not None:
                    profit = result['profit_usd']
                    if profit >= 0:
                        operation_summary += f"\n\n_Ganancia acumulada: ${profit:.2f}_"
                    else:
                        operation_summary += f"\n\n_Pérdida acumulada: ${abs(profit):.2f}_"

            elif operation_type == "REGISTER_PRODUCT":
                # Prepare product data (validation already done by Resolver)
                sku = entities.get("sku")
                name = entities.get("name")
                unit_price_cents = entities.get("unit_price_cents")
                unit_cost_cents = entities.get("unit_cost_cents", 0)  # Default to 0
                description = entities.get("description")

                product_data = {
                    "sku": sku,
                    "name": name,
                    "description": description,
                    "unit_price_cents": unit_price_cents,
                    "unit_cost_cents": unit_cost_cents
                }

                result = register_product(product_data)

                operation_summary = f"*✨ Producto creado!*\n\n"
                operation_summary += f"• {name}\n"
                operation_summary += f"• Código: _{sku}_\n"
                operation_summary += f"• Precio: *${unit_price_cents/100:.2f}*"

            elif operation_type == "UPDATE_PRODUCT_PRICE":
                # Set or change the sale price of an existing product.
                # Resolver has already turned product_ref -> product_id and
                # unit_price -> unit_price_cents.
                product_id = entities.get("product_id")
                unit_price_cents = entities.get("unit_price_cents")

                if product_id is None or unit_price_cents is None:
                    raise ValueError(
                        "Faltan datos para actualizar el precio del producto"
                    )

                row = update_product_price(product_id, int(unit_price_cents))
                result = row

                product_name = (
                    row.get("name") if row else entities.get("resolved_name", "el producto")
                )
                price_usd = unit_price_cents / 100.0
                operation_summary = (
                    f"Listo. *{product_name}* ahora se vende a *${price_usd:.2f}*."
                )

            elif operation_type == "REGISTER_PRODUCT_WITH_STOCK":
                # Atomic op: create product (price pending) + register initial stock entry.
                # Triggered by user confirming a PROPOSE_PRODUCT_CREATION turn.
                from agents.resolver import generate_sku_from_name

                name = entities.get("name")
                initial_stock = entities.get("initial_stock")

                if not name or initial_stock is None:
                    raise ValueError(
                        "Faltan datos para crear producto y registrar stock"
                    )

                sku = entities.get("sku") or generate_sku_from_name(name)

                result = register_product_with_stock({
                    "sku": sku,
                    "name": name,
                    "description": entities.get("description"),
                    "unit_price_cents": None,  # precio pendiente
                    "unit_cost_cents": entities.get("unit_cost_cents", 0),
                    "initial_stock": initial_stock,
                    "stock_reason": entities.get("stock_reason", "Entrada inicial"),
                })

                current_stock = result.get("current_stock", initial_stock)
                operation_summary = (
                    f"Listo. Cree *{name}* y registre {initial_stock} unidades de entrada "
                    f"(stock actual: {current_stock}).\n\n"
                    f"Querés cargar el precio de venta ahora o lo dejamos para la primera venta?"
                )

            elif operation_type == "ADD_STOCK":
                # ADD_STOCK can handle either single product or multiple items
                reason = entities.get("reason", "Entrada de stock")
                movement_type = entities.get("movement_type", "IN")

                items = entities.get("items", [])

                # If no items array, treat as single product
                if not items:
                    product_id = entities.get("product_id")
                    quantity = entities.get("quantity")

                    if product_id is None or quantity is None:
                        raise ValueError("Se requieren product_id y quantity para actualizar el stock")

                    items = [{
                        "product_id": product_id,
                        "quantity": quantity,
                        "resolved_name": entities.get("resolved_name", "producto")
                    }]

                # CRITICAL SAFETY CHECK: Verify NO items have resolution errors
                for item in items:
                    if "resolution_error" in item:
                        raise ValueError(item["resolution_error"])

                # Process each stock movement
                results = []
                for item in items:
                    stock_data = {
                        "product_id": item["product_id"],
                        "quantity": item["quantity"],
                        "reason": reason,
                        "movement_type": movement_type
                    }
                    result = add_stock(stock_data)
                    result["resolved_name"] = item.get("resolved_name", "producto")
                    result["quantity"] = item.get("quantity", 0)  # Preserve quantity for display
                    results.append(result)

                # Build summary
                operation_summary = f"*📦 Stock actualizado!*\n\n"
                for res in results:
                    product_name = res["resolved_name"]
                    quantity = res.get("quantity", 0)
                    current = res.get("current_stock", 0)
                    operation_summary += f"• *{product_name}*: +{quantity} unidades (stock actual: {current})\n"

            elif operation_type == "CANCEL_SALE":
                # Get the sale to cancel
                target = entities.get("target", "last")

                if target == "last":
                    # Get last sale
                    last_sale = get_last_sale()
                    if not last_sale:
                        raise ValueError("No hay ventas para cancelar")
                    sale_id = last_sale["id"]
                else:
                    # Specific sale_id
                    sale_id = int(target)

                # Cancel the sale
                result = cancel_sale(sale_id)

                operation_summary = f"*❌ Venta cancelada!*\n\n"
                operation_summary += f"• Se canceló la venta por *${result['cancelled_amount']:.2f}*\n"
                if result.get('revenue_usd') is not None:
                    operation_summary += f"\n_Ventas totales: ${result['revenue_usd']:.2f}_"
                if result.get('profit_usd') is not None:
                    profit = result['profit_usd']
                    if profit >= 0:
                        operation_summary += f"\n_Ganancia acumulada: ${profit:.2f}_"
                    else:
                        operation_summary += f"\n_Pérdida acumulada: ${abs(profit):.2f}_"

            elif operation_type == "CANCEL_EXPENSE":
                # Get the expense to cancel
                target = entities.get("target", "last")

                if target == "last":
                    # Get last expense
                    last_expense = get_last_expense()
                    if not last_expense:
                        raise ValueError("No hay gastos para cancelar")
                    expense_id = last_expense["id"]
                else:
                    # Specific expense_id
                    expense_id = int(target)

                # Cancel the expense
                result = cancel_expense(expense_id)

                operation_summary = f"*❌ Gasto cancelado!*\n\n"
                operation_summary += f"• Se canceló: {result['description']}\n"
                operation_summary += f"• Monto: *${result['cancelled_amount']:.2f}*"
                if result.get('profit_usd') is not None:
                    profit = result['profit_usd']
                    operation_summary += "\n"
                    if profit >= 0:
                        operation_summary += f"\n_Ganancia acumulada: ${profit:.2f}_"
                    else:
                        operation_summary += f"\n_Pérdida acumulada: ${abs(profit):.2f}_"

            elif operation_type == "CANCEL_STOCK":
                # Get the stock movement to cancel
                target = entities.get("target", "last")

                if target == "last":
                    # Get last stock movement
                    last_movement = get_last_stock_movement()
                    if not last_movement:
                        raise ValueError("No hay movimientos de stock para cancelar")
                    movement_id = last_movement["id"]
                else:
                    # Specific movement_id
                    movement_id = int(target)

                # Cancel the stock movement
                result = cancel_stock_movement(movement_id)

                operation_summary = f"*❌ Stock cancelado!*\n\n"
                operation_summary += f"• Se canceló entrada de stock de *{result['product_name']}*\n"
                operation_summary += f"• Cantidad cancelada: {result['cancelled_quantity']} unidades\n"
                operation_summary += f"• Stock actual: {result['current_stock']} unidades"

            elif operation_type == "CANCEL_LAST_OPERATION":
                # Detect which was the last operation and cancel it
                last_op = get_last_operation()

                if not last_op:
                    raise ValueError("No hay operaciones recientes para cancelar")

                op_type = last_op["type"]
                op_data = last_op["data"]

                if op_type == "SALE":
                    result = cancel_sale(op_data["id"])
                    operation_summary = f"*❌ Venta cancelada!*\n\n"
                    operation_summary += f"• Se canceló la venta por *${result['cancelled_amount']:.2f}*\n"
                    if result.get('revenue_usd') is not None:
                        operation_summary += f"\n_Ventas totales: ${result['revenue_usd']:.2f}_"
                    if result.get('profit_usd') is not None:
                        profit = result['profit_usd']
                        if profit >= 0:
                            operation_summary += f"\n_Ganancia acumulada: ${profit:.2f}_"
                        else:
                            operation_summary += f"\n_Pérdida acumulada: ${abs(profit):.2f}_"

                elif op_type == "EXPENSE":
                    result = cancel_expense(op_data["id"])
                    operation_summary = f"*❌ Gasto cancelado!*\n\n"
                    operation_summary += f"• Se canceló: {result['description']}\n"
                    operation_summary += f"• Monto: *${result['cancelled_amount']:.2f}*"
                    if result.get('profit_usd') is not None:
                        profit = result['profit_usd']
                        operation_summary += "\n"
                        if profit >= 0:
                            operation_summary += f"\n_Ganancia acumulada: ${profit:.2f}_"
                        else:
                            operation_summary += f"\n_Pérdida acumulada: ${abs(profit):.2f}_"

                elif op_type == "STOCK":
                    result = cancel_stock_movement(op_data["id"])
                    operation_summary = f"*❌ Stock cancelado!*\n\n"
                    operation_summary += f"• Se canceló entrada de stock de *{result['product_name']}*\n"
                    operation_summary += f"• Cantidad cancelada: {result['cancelled_quantity']} unidades\n"
                    operation_summary += f"• Stock actual: {result['current_stock']} unidades"

            elif operation_type == "DEACTIVATE_PRODUCT":
                # Deactivate a product (mark as inactive, don't delete)
                product_id = entities.get("product_id")
                product_name = entities.get("resolved_name", "producto")

                if product_id is None:
                    raise ValueError("No se pudo identificar el producto a desactivar")

                result = deactivate_product(product_id)

                operation_summary = f"*🗑️ Producto desactivado!*\n\n"
                operation_summary += f"• *{product_name}* ha sido removido del catálogo\n"
                operation_summary += f"• El producto ya no aparecerá en el inventario\n"
                operation_summary += f"• El historial de ventas se mantiene intacto"

            else:
                raise ValueError(f"Tipo de operación desconocido: {operation_type}")

            return {
                "operation_result": result,
                "messages": [{
                    "role": "assistant",
                    "content": f"[Write Agent] {operation_summary}"
                }],
                "final_answer": operation_summary if state.get("intent") == "WRITE_OPERATION" else None
            }

        except Exception as e:
            error_msg = f"Operación fallida: {str(e)}"
            return {
                "operation_result": None,
                "error": error_msg,
                "final_answer": error_msg,
                "messages": [{
                    "role": "assistant",
                    "content": f"[Write Agent] {error_msg}"
                }]
            }

    return execute_operation


def route_after_write(state: AgentState) -> str:
    """
    Determine next step after write operation.

    Args:
        state: Current agent state

    Returns:
        Name of next node
    """
    # If error, go to final answer
    if state.get("error"):
        return "final_answer"

    # If MIXED intent, go to read agent next
    if state.get("intent") == "MIXED":
        return "read_agent"

    # Otherwise, we're done (final_answer already set)
    return "final_answer"
