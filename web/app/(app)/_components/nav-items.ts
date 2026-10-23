// Nav data, in a SERVER-SAFE module (no client directive). The (app) layout is a
// server component and maps over this array; it must be the real array, not a
// client-reference proxy. Keeping it in the client nav.tsx made the server import
// resolve to a client stub, so NAV_ITEMS.map threw at runtime on the authed render
// (digest 3441644737). NavLink (which needs usePathname) stays client-side.
export const NAV_ITEMS: Array<[string, string]> = [
  ["/hoy", "Hoy"],
  ["/stock", "Stock"],
  ["/productos", "Productos"],
  ["/ventas", "Ventas"],
  ["/costos", "Costos"],
  ["/produccion", "Produccion"],
  ["/proveedores", "Proveedores"],
  ["/logistica", "Logistica"],
  ["/resultado", "Resultado"],
];
