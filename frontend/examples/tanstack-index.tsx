import { createFileRoute } from "@tanstack/react-router";
import { Storefront } from "@/components/storefront";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Storefront — Shop the Collection" },
      { name: "description", content: "Browse henleys, hoodies, denim, twill and tees in an animated circle." },
      { property: "og:title", content: "Storefront — Shop the Collection" },
      { property: "og:description", content: "Browse henleys, hoodies, denim, twill and tees." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Storefront,
});

