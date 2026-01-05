"""
Write/Operations Agent - Executes business operations through Python functions only.

Responsibilities:
- Execute business operations (register_sale, register_expense, register_product, add_stock)
- NO raw SQL generation
- Validate all required data is present
- Summarize business impact after execution
- NEVER use sql_db_query
"""
from typing import Dict, Any
from database import (
    register_sale,
    register_product,
    add_stock,
    register_expense,
    cancel_sale,
    cancel_expense,
    cancel_stock_movement,
    get_last_sale,
    get_last_expense,
    get_last_stock_movement,
    get_last_operation,
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
