import { createFileRoute } from "@tanstack/react-router";
import { ArrowDownRight } from "lucide-react";
import duo from "@/assets/campaign-duo.png.asset.json";
import pairLean from "@/assets/i.jpeg.asset.json";
import pairBack from "@/assets/l.jpeg.asset.json";
import portrait from "@/assets/n.jpeg.asset.json";
import hoodie from "@/assets/hoodie.webp.asset.json";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "All Of Us — Good things have a way of bringing us in" },
      { name: "description", content: "Thoughtful pieces for the rituals, rooms, and people that make a life feel like yours." },
      { property: "og:title", content: "All Of Us — Made for everyday together" },
      { property: "og:description", content: "Thoughtful everyday pieces: hoodies, tees and denim made to be lived in." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Index,
});

const gallery = [
  { img: hoodie.url, name: "Double-Zip Hoodie", caption: "Heather grey" },
  { img: pairLean.url, name: "Everyday Zip Set", caption: "Black / Grey" },
  { img: portrait.url, name: "Ribbed Henley", caption: "Stone grey" },
  { img: pairBack.url, name: "Lounge Trouser", caption: "Grey marl" },
];

function Index() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="bg-ink py-1.5 text-center text-xs font-medium text-ink-foreground">
        A little more room for the good things in life · Free delivery over $75
      </div>
      <header className="bg-ink text-ink-foreground">
        <div className="mx-auto flex h-20 max-w-7xl items-center justify-between px-6 md:px-20">
          <a href="/" className="font-display text-2xl tracking-[0.18em]">ALL OF US</a>
          <nav className="hidden gap-10 text-sm md:flex">
            <a href="/" className="hover:opacity-70">Home</a>
            <a href="#shop" className="hover:opacity-70">Shop</a>
            <a href="#about" className="hover:opacity-70">About</a>
            <a href="#contact" className="hover:opacity-70">Contact</a>
          </nav>
          <div className="flex items-center gap-6 text-sm">
            <a href="#" className="hidden sm:inline hover:opacity-70">Sign in</a>
            <span className="flex items-center gap-2">Bag <span className="flex h-6 w-6 items-center justify-center rounded-full border border-ink-foreground text-xs">0</span></span>
          </div>
        </div>
      </header>

      <section className="relative min-h-[calc(100vh-7rem)] overflow-hidden bg-accent">
        <img src={duo.url} alt="Two people back to back in black jackets" className="photo-mono absolute inset-0 h-full w-full object-cover" />
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-ink/80 via-ink/15 to-transparent" />
        <div className="absolute inset-x-0 bottom-0 flex flex-col gap-8 px-6 pb-8 md:flex-row md:items-end md:justify-between md:px-14 md:pb-12">
          <div className="pointer-events-none max-w-lg text-ink-foreground drop-shadow-md">
            <p className="text-[11px] font-bold tracking-[0.2em]">MADE FOR EVERYDAY TOGETHER</p>
            <h1 className="mt-4 font-display text-3xl leading-[1] drop-shadow-md sm:text-4xl md:text-5xl lg:text-6xl">
              Good things have a way of <em className="italic">bringing us in.</em>
            </h1>
            <p className="mt-4 max-w-sm text-sm leading-relaxed opacity-90 drop-shadow-md">
              Thoughtful pieces for the rituals, rooms, and people that make a life feel like yours.
            </p>
          </div>
          <a href="#shop" className="inline-flex w-fit shrink-0 items-center gap-8 border border-ink-foreground/40 bg-ink px-6 py-4 text-sm font-bold text-ink-foreground transition hover:bg-background hover:text-foreground">
            Find your something <ArrowDownRight className="h-4 w-4" />
          </a>
        </div>
      </section>

      <section id="shop" className="mx-auto max-w-7xl px-6 py-24 md:px-20">
        <div className="flex items-end justify-between">
          <div>
            <p className="text-[11px] font-bold tracking-[0.2em] text-muted-foreground">FROM THE PHOTOSHOOT</p>
            <h2 className="mt-3 font-display text-5xl">Gallery</h2>
          </div>
          <a href="#shop" className="hidden text-sm font-bold underline underline-offset-4 md:block">View all</a>
        </div>
        <div className="mt-12 grid grid-cols-2 gap-6 lg:grid-cols-4">
          {gallery.map((l) => (
            <a key={l.name} href="#shop" className="group">
              <div className="aspect-[3/4] overflow-hidden bg-muted">
                <img src={l.img} alt={l.name} loading="lazy" className="h-full w-full object-cover transition duration-700 group-hover:scale-105" />
              </div>
              <div className="mt-4 text-sm">
                <p className="font-medium">{l.name}</p>
                <p className="text-muted-foreground">{l.caption}</p>
              </div>
            </a>
          ))}
        </div>
      </section>

      <section id="about" className="grid bg-ink text-ink-foreground md:grid-cols-2">
        <img src={pairBack.url} alt="Two friends standing back to back" loading="lazy" className="h-[560px] w-full object-cover" />
        <div className="flex flex-col justify-center px-8 py-16 md:px-20">
          <p className="text-[11px] font-bold tracking-[0.2em] opacity-70">OUR STORY</p>
          <h2 className="mt-6 font-display text-5xl leading-tight">Made by friends, <em>for all of us.</em></h2>
          <p className="mt-6 max-w-md leading-relaxed opacity-80">
            Heavyweight fleece, honest denim and soft ribbed cotton — pieces cut roomy, built to last, and made to be shared.
          </p>
          <a href="#shop" className="mt-10 inline-flex w-fit items-center gap-8 border border-ink-foreground bg-background px-6 py-4 text-sm font-bold text-foreground transition hover:bg-ink hover:text-ink-foreground">
            Shop the collection <ArrowDownRight className="h-4 w-4" />
          </a>
        </div>
      </section>

      <footer id="contact" className="mx-auto flex max-w-7xl flex-col justify-between gap-6 px-6 py-14 text-sm md:flex-row md:px-20">
        <span className="font-display text-xl tracking-[0.18em]">ALL OF US</span>
        <span className="text-muted-foreground">hello@allofus.store · © 2026 All Of Us</span>
      </footer>
    </div>
  );
}
