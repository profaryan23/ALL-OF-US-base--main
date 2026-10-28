export type CartItem = {
  product: string;
  color: string;
  size: string;
  quantity: number;
  price: number;
  image: string;
  filter?: string | undefined;
};

export const cartKey = (item: Pick<CartItem, "product" | "color" | "size">) =>
  JSON.stringify([item.product, item.color, item.size]);

export function addCartItem(cart: CartItem[], item: CartItem): CartItem[] {
  if (!Number.isInteger(item.quantity) || item.quantity < 1 || !item.size || !item.color) return cart;
  const key = cartKey(item);
  const existing = cart.find((row) => cartKey(row) === key);
  return existing
    ? cart.map((row) => cartKey(row) === key ? { ...row, quantity: row.quantity + item.quantity } : row)
    : [...cart, { ...item }];
}

export function setCartQuantity(cart: CartItem[], key: string, quantity: number): CartItem[] {
  if (!Number.isInteger(quantity) || quantity < 1) return cart;
  return cart.map((row) => cartKey(row) === key ? { ...row, quantity } : row);
}

export const cartCount = (cart: CartItem[]) => cart.reduce((sum, row) => sum + row.quantity, 0);
export const cartTotal = (cart: CartItem[]) => cart.reduce((sum, row) => sum + row.quantity * row.price, 0);
export const formatPrice = (price: number) => `Rs ${price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;