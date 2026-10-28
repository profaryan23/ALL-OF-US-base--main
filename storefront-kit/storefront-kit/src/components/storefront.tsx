import { useState } from "react";
import { Minus, Plus, ShoppingBag } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DemoCart } from "@/components/demo-cart";
import { addCartItem, cartCount, formatPrice, type CartItem } from "@/lib/cart";

import henleyGrey from "@/assets/henley-grey.png";
import hoodieRed from "@/assets/hoodie-red.png";
import jeansBlue from "@/assets/jeans-blue.png";
import twillPantGreen from "@/assets/twill-pant-green.png";
import twillJacketGreen from "@/assets/twill-jacket-green.png";
import tankBlack from "@/assets/tank-black.png";
import fullsleeveWhite from "@/assets/fullsleeve-white.png";

type Color = { name: string; swatch: string; filter?: string };
const C = {
  black: { name: "Black", swatch: "var(--sw-black)", filter: "grayscale(1) brightness(0.35) contrast(1.15)" },
  white: { name: "White", swatch: "var(--sw-white)", filter: "grayscale(1) invert(1) brightness(1.08)" },
  grey: { name: "Grey", swatch: "var(--sw-grey)", filter: "grayscale(1) brightness(0.82) contrast(0.95)" },
  red: { name: "Red", swatch: "var(--sw-red)" },
  blue: { name: "Blue", swatch: "var(--sw-blue)" },
  green: { name: "Green", swatch: "var(--sw-green)" },
} satisfies Record<string, Color>;

const topSizes = ["M", "L", "XL"];
const pantSizes = ["28", "29", "30", "31", "32", "33", "34"];
// Placeholder catalog information for the explicitly requested demo store.
const products: { name: string; tag: string; img: string; colors: Color[]; sizes: string[]; price: number; description: string }[] = [
  { name: "Henley", tag: "Tops", img: henleyGrey, colors: [C.grey, C.black], sizes: topSizes, price: 1200, description: "An everyday henley with a button neckline and an easy, relaxed silhouette." },
  { name: "Zipped Hoodie", tag: "Outerwear", img: hoodieRed, colors: [C.red, C.black, C.grey], sizes: topSizes, price: 2600, description: "A full-zip hoodie with a hood and front pockets, made for everyday layering." },
  { name: "Denim Baggy Jeans", tag: "Bottoms", img: jeansBlue, colors: [C.blue, C.black], sizes: pantSizes, price: 2800, description: "Baggy denim jeans with a wide-leg silhouette and a laid-back look." },
  { name: "Twill Pant", tag: "Bottoms", img: twillPantGreen, colors: [C.green, C.black], sizes: pantSizes, price: 2200, description: "Straight-cut twill pants with a clean finish for an everyday wardrobe." },
  { name: "Twill Jacket", tag: "Outerwear", img: twillJacketGreen, colors: [C.green, C.black], sizes: topSizes, price: 3200, description: "A structured twill jacket with a classic collar and front pockets." },
  { name: "Sleeveless Tee", tag: "T-Shirts", img: tankBlack, colors: [C.black, C.white], sizes: topSizes, price: 800, description: "A minimal sleeveless tee with an easy fit for warm days and layering." },
  { name: "Full Sleeve Tee", tag: "T-Shirts", img: fullsleeveWhite, colors: [C.white, C.black], sizes: topSizes, price: 1100, description: "A versatile long-sleeve tee with a simple crew neckline." },
];

// Neutral variants (grey/black/white) reuse the base photo with a grayscale filter.
const tint = (s: string, pct: number) => `color-mix(in oklab, ${s} ${pct}%, var(--card))`;

// The seam ring is drawn in ~pixel units so the dash pattern reads as stitches,
// and non-scaling strokes keep the thread hairline at any rendered size.
const RING_BOX = 340;
const RING_R = 167;
const STITCH_DASH = 12;
const STITCH_GAP = 10;
// A whole number of stitches, in even runs between products, so the seam closes
// on itself with no mismatched stitch at the join.
const STITCHES =
  Math.ceil(
    Math.round((2 * Math.PI * RING_R) / (STITCH_DASH + STITCH_GAP)) / products.length,
  ) * products.length;
const SEAM_LENGTH = STITCHES * (STITCH_DASH + STITCH_GAP);

export function Storefront() {
  const [active, setActive] = useState<number | null>(null);
  const [colorIdx, setColorIdx] = useState(0);
  const [size, setSize] = useState("");
  const [quantity, setQuantity] = useState(1);
  const [cart, setCart] = useState<CartItem[]>([]);
  const [cartOpen, setCartOpen] = useState(false);
  const [notice, setNotice] = useState("");
  const p = active !== null ? products[active] : undefined;
  const color = p ? (p.colors[colorIdx] ?? p.colors[0]) : undefined;

  return (
    <main className="min-h-screen overflow-x-clip bg-background px-4 py-14">
      <div className="mx-auto mb-6 flex max-w-5xl justify-end">
        <Button variant="outline" onClick={() => setCartOpen(true)} aria-label={`Open shopping bag, ${cartCount(cart)} items`}>
          <ShoppingBag /> Bag <span className="tabular-nums">({cartCount(cart)})</span>
        </Button>
      </div>
      <header className="mb-10 text-center">
        <p className="text-xs uppercase tracking-[0.4em] text-muted-foreground">The Collection</p>
        <h1 className="font-display mt-3 text-5xl md:text-6xl">Shop Essentials</h1>
      </header>

      <div className="orbit-stage mx-auto">
        <svg className="orbit-ring" viewBox={`0 0 ${RING_BOX} ${RING_BOX}`} aria-hidden="true">
          {/* the continuous thread the seam is sewn with: hairline, barely there */}
          <circle
            cx={RING_BOX / 2}
            cy={RING_BOX / 2}
            r={RING_R}
            fill="none"
            stroke="var(--thread)"
            strokeWidth="1"
            opacity="0.2"
            vectorEffect="non-scaling-stroke"
          />
          {/* the stitches: clean, evenly spaced dashes lying on that thread */}
          <circle
            className="seam-stitch"
            cx={RING_BOX / 2}
            cy={RING_BOX / 2}
            r={RING_R}
            fill="none"
            stroke="var(--thread)"
            strokeWidth="1.6"
            strokeDasharray={`${STITCH_DASH} ${STITCH_GAP}`}
            pathLength={SEAM_LENGTH}
            strokeLinecap="round"
            vectorEffect="non-scaling-stroke"
          />
        </svg>
        <div className="orbit">
          {products.map((item, i) => {
            const angle = (360 / products.length) * i;
            return (
              <div key={item.name} className="orbit-slot" style={{ ["--a" as string]: `${angle}deg` }}>
                <Button variant="ghost"
                  onClick={() => { setActive(i); setColorIdx(0); setSize(""); setQuantity(1); setNotice(""); }}
                  className={`orbit-item ${active === i ? "orbit-item-active" : ""}`}
                  style={{ background: tint("var(--sw-grey)", 14) }}
                  aria-label={item.name}
                >
                  <img
                    src={item.img}
                    alt={item.name}
                    loading="lazy"
                    width={1024}
                    height={1024}
                    className="product-img"
                    style={{ filter: item.colors[0]?.filter }}
                  />
                  <span className="orbit-label">{item.name}</span>
                </Button>
              </div>
            );
          })}
        </div>
        <div className="orbit-center">
          {p && color ? (
            <div
              key={p.name + color.name}
              className="center-pop h-full w-full rounded-full flex items-center justify-center"
              style={{ background: tint("var(--sw-grey)", 12) }}
            >
              <img
                src={p.img}
                alt={`${p.name} in ${color.name}`}
                loading="lazy"
                width={1024}
                height={1024}
                className="product-img"
                style={{ filter: color.filter }}
              />
            </div>
          ) : (
            <p className="px-6 text-center text-sm text-muted-foreground">Click a product</p>
          )}
        </div>
      </div>

      {p && color && (
        <section key={p.name} className="details-in mx-auto mt-12 max-w-md text-center">
          <p className="text-xs uppercase tracking-[0.25em] text-muted-foreground">{p.tag}</p>
          <h2 className="font-display mt-1 text-4xl">{p.name}</h2>
          <p className="mt-3 text-lg">{formatPrice(p.price)} <span className="text-xs text-muted-foreground">· Demo price</span></p>
          <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{p.description}</p>
          <p className="mt-5 text-sm">Colour: {color.name}</p>
          <div className="mt-4 flex justify-center gap-3">
            {p.colors.map((c, idx) => (
              <Button variant="ghost" size="icon"
                key={c.name}
                aria-label={c.name}
                aria-pressed={idx === colorIdx}
                onClick={() => { setColorIdx(idx); setNotice(""); }}
                className={`swatch h-8 w-8 rounded-full ${idx === colorIdx ? "swatch-active" : ""}`}
                style={{ background: c.swatch }}
              />
            ))}
          </div>
          <fieldset className="mt-6">
            <legend className="w-full text-sm mb-3">Choose size</legend>
            <div className="flex flex-wrap justify-center gap-2">
              {p.sizes.map((value) => <Button key={value} variant={size === value ? "default" : "outline"} aria-pressed={size === value} aria-label={`Size ${value}`} className="min-w-11" onClick={() => { setSize(value); setNotice(""); }}>{value}</Button>)}
            </div>
          </fieldset>
          <div className="mt-6 flex items-center justify-center gap-3">
            <span className="text-sm mr-2">Quantity</span>
            <Button variant="outline" size="icon" aria-label="Decrease quantity" disabled={quantity <= 1} onClick={() => setQuantity((q) => q - 1)}><Minus /></Button>
            <span className="w-8 text-center tabular-nums" aria-live="polite">{quantity}</span>
            <Button variant="outline" size="icon" aria-label="Increase quantity" onClick={() => setQuantity((q) => q + 1)}><Plus /></Button>
          </div>
          <Button size="lg" className="mt-6 w-full" disabled={!size} onClick={() => {
            setCart((rows) => addCartItem(rows, { product: p.name, color: color.name, size, quantity, price: p.price, image: p.img, filter: color.filter }));
            setNotice(`${quantity} × ${p.name} · ${color.name} · ${size} added to bag`);
          }}><ShoppingBag /> Add to bag</Button>
          <p className="mt-3 min-h-5 text-xs text-muted-foreground" role="status">{notice || (!size ? "Select a size" : "")}</p>
          {notice && <Button variant="link" onClick={() => setCartOpen(true)}>View bag ({cartCount(cart)})</Button>}

        </section>
      )}
      <DemoCart items={cart} setItems={setCart} open={cartOpen} onOpenChange={setCartOpen} />
    </main>
  );
}
