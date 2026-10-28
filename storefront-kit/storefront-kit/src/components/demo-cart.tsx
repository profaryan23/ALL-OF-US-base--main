import { useState } from "react";
import { ArrowLeft, ArrowRight, Check, Minus, Plus, ShoppingBag, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { cartCount, cartKey, cartTotal, formatPrice, setCartQuantity, type CartItem } from "@/lib/cart";

type Props = {
  items: CartItem[];
  setItems: React.Dispatch<React.SetStateAction<CartItem[]>>;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function DemoCart({ items, setItems, open, onOpenChange }: Props) {
  const [stage, setStage] = useState<"cart" | "review" | "complete">("cart");
  const [order, setOrder] = useState<CartItem[]>([]);
  const shown = stage === "complete" ? order : items;
  const total = cartTotal(shown);
  const changeOpen = (next: boolean) => {
    onOpenChange(next);
    if (!next) setStage("cart");
  };

  return (
    <Dialog open={open} onOpenChange={changeOpen}>
      <DialogContent className="max-w-xl max-h-[90dvh] w-[calc(100%-2rem)] overflow-y-auto rounded-lg p-5 sm:p-7">
        <DialogTitle className="font-display text-3xl pr-6">
          {stage === "complete" ? "Demo order complete" : stage === "review" ? "Review your order" : "Your shopping bag"}
        </DialogTitle>
        <DialogDescription>
          {stage === "complete" ? "No payment was taken and no real order was placed." : `Demo checkout · ${cartCount(shown)} items · Sample prices`}
        </DialogDescription>
        {stage === "complete" && <div className="flex items-center gap-2 text-sm"><Check className="size-5" />Your selections are confirmed for this demo.</div>}
        {shown.length === 0 ? (
          <div className="py-12 text-center">
            <ShoppingBag className="mx-auto mb-4 size-8 text-muted-foreground" />
            <p>Your bag is empty.</p>
            <Button variant="outline" className="mt-5" onClick={() => changeOpen(false)}>Continue shopping</Button>
          </div>
        ) : (
          <>
            <div className="divide-y divide-border">
              {shown.map((item) => {
                const key = cartKey(item);
                return (
                  <div key={key} className="flex gap-4 py-5">
                    <img src={item.image} style={{ filter: item.filter }} alt={`${item.product} in ${item.color}`} className="h-20 w-20 shrink-0 object-contain bg-muted rounded-md" />
                    <div className="min-w-0 flex-1">
                      <h3 className="font-medium break-words">{item.product}</h3>
                      <p className="mt-1 text-sm text-muted-foreground">{item.color} · Size {item.size}</p>
                      <p className="mt-1 text-sm">{formatPrice(item.price)} each</p>
                      {stage === "cart" ? (
                        <div className="mt-3 flex flex-wrap items-center gap-2">
                          <Button size="icon" variant="outline" aria-label={`Decrease ${item.product} ${item.color} ${item.size}`} disabled={item.quantity <= 1} onClick={() => setItems((rows) => setCartQuantity(rows, key, item.quantity - 1))}><Minus /></Button>
                          <span className="min-w-7 text-center tabular-nums" aria-label="Item quantity">{item.quantity}</span>
                          <Button size="icon" variant="outline" aria-label={`Increase ${item.product} ${item.color} ${item.size}`} onClick={() => setItems((rows) => setCartQuantity(rows, key, item.quantity + 1))}><Plus /></Button>
                          <Button size="icon" variant="ghost" aria-label={`Remove ${item.product} ${item.color} ${item.size}`} onClick={() => setItems((rows) => rows.filter((row) => cartKey(row) !== key))}><Trash2 /></Button>
                        </div>
                      ) : <p className="mt-2 text-sm">Quantity: {item.quantity}</p>}
                      <p className="mt-2 font-medium tabular-nums">{formatPrice(item.price * item.quantity)}</p>
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="border-t border-border pt-5 flex justify-between font-medium"><span>Demo total</span><span>{formatPrice(total)}</span></div>
            {stage === "cart" && <Button size="lg" onClick={() => setStage("review")}>Proceed to demo checkout <ArrowRight /></Button>}
            {stage === "review" && <>
              <p className="text-xs text-muted-foreground">Demo only. Shipping and payment are not collected.</p>
              <Button size="lg" onClick={() => { setOrder(items.map((item) => ({ ...item }))); setItems([]); setStage("complete"); }}>Place demo order <Check /></Button>
              <Button variant="ghost" onClick={() => setStage("cart")}><ArrowLeft /> Back to bag</Button>
            </>}
            {stage === "complete" && <Button onClick={() => changeOpen(false)}>Continue shopping <ArrowRight /></Button>}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}