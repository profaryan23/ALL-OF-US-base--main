# Shop Essentials — integration folder

Animated stitched-circle apparel selector with product details, size/color/quantity selection, and a multi-item demo shopping bag. Black, white, and grey page theme; original apparel colors are preserved.

## Merge into an existing React project

1. Back up your existing project. Merge the contents of `src/` into your project's `src/` directory. Do not replace existing files with matching names without reviewing them. Rename or adjust imports if your project already has `storefront`, `demo-cart`, `cart`, `utils`, `button`, or `dialog` files.
2. Install any missing packages from `dependencies.json`. Merge dependencies into your package.json; do not replace it with dependencies.json. React 19 and Tailwind CSS v4 are used here. The reusable component does not require TanStack Router.
3. Configure `@/` to resolve to your `src/` directory in your bundler and TypeScript configuration, or change the imports to relative paths. Your bundler must support PNG imports. The seven product images are included.
4. Merge `src/styles.css` with your global stylesheet. Keep CSS imports at the top and include the `@theme inline` mappings, neutral theme overrides, product swatches, orbit styles, and animation rules. **This stylesheet contains global body, :root, and .dark rules: importing it unchanged changes the host application's theme.** Review those rules if only this section should be monochrome. The package uses Tailwind v4; do not paste its directives unchanged into a Tailwind v3 project. Ensure Tailwind scans the copied files.
5. Render the component in your existing page:

```tsx
import { Storefront } from "@/components/storefront";

export function ShopPage() {
  return <Storefront />;
}
```

6. For a TanStack Router project, `examples/tanstack-index.tsx` demonstrates route metadata and rendering. Merge it with your existing route; do not blindly replace your homepage. Keep your existing router, root layout, providers, and navigation. For any other React router, render Storefront in your normal page and set metadata using that project's conventions.
7. Optionally load Fraunces weight 500 through a stylesheet link in your document head. Without it the display headings use Georgia. Do not add a remote CSS @import.

## Customize products

The catalog in `src/components/storefront.tsx` contains product names, categories, descriptions, sizes, color choices, images, and **sample prices in Rs**. Replace prices and descriptions with your real details. Neutral apparel variants use filters on each base image; these are demonstrations rather than exact variant photography.

## Demo limits

The cart lives only in React memory and resets on refresh or when the component unmounts. Matching product/color/size variants merge quantities; other variants remain separate lines. Shoppers can review, adjust, remove, and confirm multiple selections together. No real payment, shipping, inventory check, account, or order submission exists. Demo confirmation clears the bag and displays a local confirmation only.

## Tests and compatibility

`src/lib/cart.test.ts` contains six pure cart behavior tests. If Vitest is installed, run `bunx vitest run src/lib/cart.test.ts` (or the equivalent package-runner command). The storefront and demo order flow were checked in the originating React 19 / Tailwind v4 app. Integration into your existing project has not been tested because its source was not supplied.

This folder is an integration kit, not a standalone app: no generated output, node_modules, Git metadata, credentials, or framework bootstrap are included.
