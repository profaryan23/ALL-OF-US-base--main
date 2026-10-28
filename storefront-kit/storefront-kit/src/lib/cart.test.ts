import { describe, expect, it } from "vitest";
import { addCartItem, cartCount, cartKey, cartTotal, setCartQuantity, type CartItem } from "./cart";

const henley: CartItem = { product: "Henley", color: "Grey", size: "M", quantity: 2, price: 1200, image: "henley.png" };

describe("demo apparel cart", () => {
  it("combines multiple products in one order", () => {
    const cart = addCartItem(addCartItem([], henley), { ...henley, product: "Zipped Hoodie", color: "Red", quantity: 3 });
    expect(cart).toHaveLength(2);
    expect(cartCount(cart)).toBe(5);
  });
  it("keeps different sizes separate", () => {
    expect(addCartItem([henley], { ...henley, size: "XL" })).toHaveLength(2);
  });
  it("keeps different colors separate", () => {
    expect(addCartItem([henley], { ...henley, color: "Black" })).toHaveLength(2);
  });
  it("merges quantities for matching product, size and color", () => {
    expect(addCartItem([henley], { ...henley, quantity: 3 })).toEqual([{ ...henley, quantity: 5 }]);
  });
  it("updates quantity and calculates line totals", () => {
    const cart = setCartQuantity([henley], cartKey(henley), 4);
    expect(cartTotal(cart)).toBe(4800);
  });
  it("rejects invalid quantities and missing sizes", () => {
    expect(addCartItem([], { ...henley, quantity: 0 })).toEqual([]);
    expect(addCartItem([], { ...henley, size: "" })).toEqual([]);
    expect(setCartQuantity([henley], cartKey(henley), 1.5)).toEqual([henley]);
  });
});