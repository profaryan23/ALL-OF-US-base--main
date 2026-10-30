import React, { useState, useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

// Expanded Product Catalog with Color Variants and Technical Specs
const PRODUCTS_DATA = [
  {
    id: 'prod-1',
    name: 'Oversized Structured Blazer',
    subtitle: 'Sculpted Wool',
    category: 'Outerwear',
    price: '$980',
    description: 'Precision-tailored from double-woven Italian virgin wool. Features padded drop shoulders, exaggerated lapels, and custom matte horn buttons.',
    material: '100% Virgin Wool, Cupro Lining',
    fit: 'Relaxed / Oversized Silhouette',
    stock: 'In Stock (4 items remaining)',
    tag: 'Edition 01',
    colors: [
      { name: 'Noir', hex: '#111111', image: 'https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?q=80&w=1000&auto=format&fit=crop' },
      { name: 'Slate', hex: '#4A5568', image: 'https://images.unsplash.com/photo-1539109136881-3be0616acf4b?q=80&w=1000&auto=format&fit=crop' },
      { name: 'Espresso', hex: '#2C1D11', image: 'https://images.unsplash.com/photo-1509631179647-0177331693ae?q=80&w=1000&auto=format&fit=crop' }
    ]
  },
  {
    id: 'prod-2',
    name: 'Cashmere Drape Overcoat',
    subtitle: 'Mongolian Cashmere',
    category: 'Coats',
    price: '$1,450',
    description: 'Unstructured double-faced coat crafted from ethically harvested Grade-A Mongolian cashmere with raw edge seam details.',
    material: '90% Mongolian Cashmere, 10% Silk',
    fit: 'Tailored Floor-Length Drape',
    stock: 'Low Stock',
    tag: 'Edition 02',
    colors: [
      { name: 'Oatmeal', hex: '#D6C7B2', image: 'https://images.unsplash.com/photo-1539109136881-3be0616acf4b?q=80&w=1000&auto=format&fit=crop' },
      { name: 'Obsidian', hex: '#0B0B0B', image: 'https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?q=80&w=1000&auto=format&fit=crop' },
      { name: 'Olive', hex: '#3B413A', image: 'https://images.unsplash.com/photo-1496747611176-843222e1e57c?q=80&w=1000&auto=format&fit=crop' }
    ]
  },
  {
    id: 'prod-3',
    name: 'Sculptural Leather Tote',
    subtitle: 'Calfskin Geometry',
    price: '$1,120',
    category: 'Leather Goods',
    description: 'Handcrafted architectural tote in full-grain Tuscan calfskin with brushed palladium geometric hardware and concealed magnetic closure.',
    material: 'Full-Grain Calfskin Leather',
    fit: 'One Size (38 x 42 x 14 cm)',
    stock: 'In Stock',
    tag: 'Edition 03',
    colors: [
      { name: 'Cognac', hex: '#8B4513', image: 'https://images.unsplash.com/photo-1584917865442-de89df76afd3?q=80&w=1000&auto=format&fit=crop' },
      { name: 'Jet Black', hex: '#181818', image: 'https://images.unsplash.com/photo-1543163521-1bf539c55dd2?q=80&w=1000&auto=format&fit=crop' }
    ]
  },
  {
    id: 'prod-4',
    name: 'Pleated Silk Trousers',
    subtitle: 'Mulberry Silk Crepe',
    category: 'Bottoms',
    price: '$680',
    description: 'High-waisted wide-leg trousers feature deep front pleats, hidden side slip pockets, and fluid drape in heavyweight Mulberry silk crepe.',
    material: '100% Mulberry Silk',
    fit: 'High-Rise Wide Leg',
    stock: 'In Stock',
    tag: 'Edition 04',
    colors: [
      { name: 'Cream', hex: '#FDFBF7', image: 'https://images.unsplash.com/photo-1509631179647-0177331693ae?q=80&w=1000&auto=format&fit=crop' },
      { name: 'Charcoal', hex: '#2F3640', image: 'https://images.unsplash.com/photo-1576995853123-5a10305d93c0?q=80&w=1000&auto=format&fit=crop' }
    ]
  },
  {
    id: 'prod-5',
    name: 'Minimalist Leather Mule',
    subtitle: 'Nappa Lambskin',
    category: 'Footwear',
    price: '$590',
    description: 'Sculpted square-toe mule constructed with ultra-soft Italian lambskin, hand-turned soles, and a low architectural block heel.',
    material: 'Nappa Lambskin, Leather Sole',
    fit: 'True to Size',
    stock: 'In Stock',
    tag: 'Edition 05',
    colors: [
      { name: 'Alabaster', hex: '#EAE6DF', image: 'https://images.unsplash.com/photo-1543163521-1bf539c55dd2?q=80&w=1000&auto=format&fit=crop' },
      { name: 'Noir', hex: '#111111', image: 'https://images.unsplash.com/photo-1584917865442-de89df76afd3?q=80&w=1000&auto=format&fit=crop' }
    ]
  },
  {
    id: 'prod-6',
    name: 'Wool Wrap Trench Coat',
    subtitle: 'Melton Wool Blend',
    category: 'Outerwear',
    price: '$1,320',
    description: 'An understated trench featuring storm flaps, exaggerated notched lapels, and a removable self-tie belt for versatile structural styling.',
    material: '85% Melton Wool, 15% Polyamide',
    fit: 'Classic Oversized Fit',
    stock: 'Pre-Order',
    tag: 'Edition 06',
    colors: [
      { name: 'Camel', hex: '#C19A6B', image: 'https://images.unsplash.com/photo-1496747611176-843222e1e57c?q=80&w=1000&auto=format&fit=crop' },
      { name: 'Midnight', hex: '#1A2332', image: 'https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?q=80&w=1000&auto=format&fit=crop' }
    ]
  },
  {
    id: 'prod-7',
    name: 'Monochrome Rib Knit Top',
    subtitle: 'Fine Seamless Merino',
    category: 'Knitwear',
    price: '$390',
    description: 'Seamless 3D-knit second-skin top crafted from ultrafine Australian merino wool. Ergonomic rib placement for natural contouring.',
    material: '100% Extrafine Merino Wool',
    fit: 'Fitted Contour Shape',
    stock: 'In Stock',
    tag: 'Edition 07',
    colors: [
      { name: 'Ecrú', hex: '#F3EFE0', image: 'https://images.unsplash.com/photo-1576995853123-5a10305d93c0?q=80&w=1000&auto=format&fit=crop' },
      { name: 'Sage', hex: '#8F9779', image: 'https://images.unsplash.com/photo-1509631179647-0177331693ae?q=80&w=1000&auto=format&fit=crop' }
    ]
  }
];

export default function App() {
  // Continuous index allows fractional tire positions for endless revolving wheel math
  const [currentIndex, setCurrentIndex] = useState(3.0);
  const [containerWidth, setContainerWidth] = useState(180);
  const [isInteracting, setIsInteracting] = useState(false);
  
  // Track selected color index per product ID
  const [selectedColors, setSelectedColors] = useState({});
  
  const totalItems = PRODUCTS_DATA.length;
  const interactionTimeoutRef = useRef(null);
  const wheelAccumulatorRef = useRef(0);

  // Responsive dynamic horizontal step spacing calculation
  useEffect(() => {
    const updateSpacing = () => {
      setContainerWidth(window.innerWidth < 640 ? 115 : window.innerWidth < 1024 ? 145 : 175);
    };
    updateSpacing();
    window.addEventListener('resize', updateSpacing);
    return () => window.removeEventListener('resize', updateSpacing);
  }, []);

  // Flag user interaction to temporarily pause ambient auto-drift
  const triggerUserInteraction = useCallback(() => {
    setIsInteracting(true);
    if (interactionTimeoutRef.current) clearTimeout(interactionTimeoutRef.current);
    interactionTimeoutRef.current = setTimeout(() => {
      setIsInteracting(false);
    }, 3200); // Resume endless revolving drift after 3.2s of inactivity
  }, []);

  // Continuous Ambient Motion Loop (Endless Tire Rotation)
  useEffect(() => {
    if (isInteracting) return;
    
    let animationFrameId;
    const tireSpeed = 0.003; // Gentle ambient revolving speed

    const ambientTireLoop = () => {
      setCurrentIndex((prev) => prev + tireSpeed);
      animationFrameId = requestAnimationFrame(ambientTireLoop);
    };

    animationFrameId = requestAnimationFrame(ambientTireLoop);
    return () => cancelAnimationFrame(animationFrameId);
  }, [isInteracting]);

  // Modulo math for smooth infinite continuous wrap
  const getWrappedIndex = useCallback((val) => {
    return ((val % totalItems) + totalItems) % totalItems;
  }, [totalItems]);

  // Smooth Snap to Target Index (Finds shortest path in continuous wheel space)
  const snapToNearestIndex = useCallback((targetIndex) => {
    triggerUserInteraction();
    setCurrentIndex(targetIndex);
  }, [triggerUserInteraction]);

  // Scroll Wheel Navigation (Trackpad/mouse continuous revolving)
  const handleWheel = useCallback((e) => {
    e.preventDefault();
    triggerUserInteraction();

    const delta = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY;
    wheelAccumulatorRef.current += delta * 0.0022;

    if (Math.abs(wheelAccumulatorRef.current) >= 0.2) {
      setCurrentIndex((prev) => prev + wheelAccumulatorRef.current);
      wheelAccumulatorRef.current = 0;
    }
  }, [triggerUserInteraction]);

  // Keyboard Arrow Keys Navigation
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'ArrowLeft') {
        snapToNearestIndex(Math.round(currentIndex - 1));
      } else if (e.key === 'ArrowRight') {
        snapToNearestIndex(Math.round(currentIndex + 1));
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [currentIndex, snapToNearestIndex]);

  // Handle Touch/Drag Gesture
  const handleDrag = (_, info) => {
    triggerUserInteraction();
    const indexDelta = -info.delta.x / containerWidth;
    setCurrentIndex((prev) => prev + indexDelta);
  };

  const handleDragEnd = (_, info) => {
    triggerUserInteraction();
    const velocityFactor = info.velocity.x / 800;
    const target = Math.round(currentIndex - velocityFactor);
    snapToNearestIndex(target);
  };

  // Calculate active focused product index wrapped to array range
  const activeNormalizedFloat = getWrappedIndex(currentIndex);
  const activeDiscreteIndex = Math.round(activeNormalizedFloat) % totalItems;
  const activeProduct = PRODUCTS_DATA[activeDiscreteIndex];

  // Active color option for selected item
  const activeColorIndex = selectedColors[activeProduct.id] || 0;
  const activeColor = activeProduct.colors[activeColorIndex] || activeProduct.colors[0];

  const handleSelectColor = (productId, colorIdx) => {
    triggerUserInteraction();
    setSelectedColors((prev) => ({
      ...prev,
      [productId]: colorIdx
    }));
  };

  return (
    <div 
      onWheel={handleWheel}
      className="min-h-screen bg-[#030302] text-[#F1F1F1] font-sans antialiased overflow-x-hidden selection:bg-amber-500/20 selection:text-amber-200 relative flex flex-col justify-between select-none pb-12"
    >
      
      {/* Background Ambient Luxury Radial Glows */}
      <div className="fixed inset-0 pointer-events-none z-0">
        <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[1200px] h-[600px] bg-gradient-to-tr from-amber-600/10 via-neutral-500/5 to-amber-700/15 blur-[200px] rounded-full opacity-60" />
        <div className="absolute inset-0 bg-[radial-gradient(#ffffff08_1px,transparent_1px)] [background-size:32px_32px] opacity-20" />
      </div>

      {/* Ultra-Minimal Brand Header */}
      <header className="relative z-20 max-w-7xl mx-auto w-full px-8 py-8 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="w-8 h-8 rounded-full border border-amber-500/30 flex items-center justify-center bg-white/5 backdrop-blur-md">
            <span className="font-serif italic text-base text-amber-200">F</span>
          </div>
          <span className="text-xs tracking-[0.35em] uppercase text-neutral-300 font-medium">
            FLUXA / NOVA
          </span>
        </div>

        <div className="text-[10px] text-neutral-500 tracking-[0.25em] uppercase font-mono">
          {String(activeDiscreteIndex + 1).padStart(2, '0')} / {String(totalItems).padStart(2, '0')}
        </div>
      </header>

      {/* Main Gesture & Endless Revolving Wheel Stage */}
      <main className="relative z-10 flex-1 flex flex-col justify-center px-4 max-w-7xl mx-auto w-full">
        
        {/* Editorial Heading */}
        <div className="text-center max-w-3xl mx-auto mb-4 sm:mb-8 space-y-2 pointer-events-none">
          <motion.div 
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
            className="text-[10px] sm:text-[11px] tracking-[0.35em] uppercase text-amber-200/80 font-medium"
          >
            Endless 3D Tire Arc Kinematics
          </motion.div>

          <motion.h1 
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.1 }}
            className="text-2xl sm:text-4xl md:text-5xl font-light tracking-tight text-neutral-100 leading-[1.15]"
          >
            Redefining Everyday Wear With <span className="font-serif italic font-normal text-amber-100">Timeless Minimalism</span>
          </motion.h1>
        </div>

        {/* Endless Revolving 3D Arc Card Surface */}
        <div className="relative w-full max-w-6xl mx-auto h-[420px] sm:h-[480px] flex items-center justify-center">
          
          <motion.div 
            drag="x"
            dragConstraints={{ left: 0, right: 0 }}
            dragElastic={0.15}
            onDrag={handleDrag}
            onDragEnd={handleDragEnd}
            className="relative w-full h-full flex items-center justify-center cursor-grab active:cursor-grabbing touch-pan-y"
          >
            <AnimatePresence mode="sync">
              {PRODUCTS_DATA.map((product, index) => {
                
                /*
                 * ENDLESS ROTATING TIRE ARITHMETIC:
                 * Find shortest cyclic distance delta in continuous modulo space [-totalItems/2, totalItems/2]
                 */
                let rawDelta = index - activeNormalizedFloat;
                // Wrap delta onto continuous endless circle boundary
                let delta = ((rawDelta + totalItems / 2) % totalItems + totalItems) % totalItems - totalItems / 2;

                const absDelta = Math.abs(delta);
                const isActive = absDelta < 0.5;

                // Tire Arc Kinematics Equations
                const rotateZ = delta * 12; // Outward tilt degrees
                const translateY = Math.pow(absDelta, 1.8) * 18; // Quadratic parabolic drop
                const translateX = delta * containerWidth; // X position spacing
                const scale = Math.max(0.65, 1.12 - absDelta * 0.13); // Scale decay
                const zIndex = Math.round(50 - absDelta * 10);
                const opacity = Math.max(0, 1 - absDelta * 0.22);

                // Check active color custom image override
                const cardColorIdx = selectedColors[product.id] || 0;
                const cardImg = product.colors[cardColorIdx]?.image || product.colors[0].image;

                return (
                  <motion.div
                    key={product.id}
                    layout
                    onClick={() => {
                      // Calculate shortest integer step direction for target click
                      const targetIndex = currentIndex + delta;
                      snapToNearestIndex(Math.round(targetIndex));
                    }}
                    animate={{
                      x: translateX,
                      y: translateY,
                      rotateZ: rotateZ,
                      scale: scale,
                      zIndex: zIndex,
                      opacity: opacity,
                    }}
                    transition={{
                      type: "spring",
                      stiffness: 220,
                      damping: 26,
                      mass: 0.75
                    }}
                    whileHover={isActive ? { scale: 1.16 } : { scale: scale * 1.05 }}
                    className={`absolute rounded-3xl p-3 bg-neutral-900/85 border backdrop-blur-2xl transition-shadow duration-500 w-[210px] sm:w-[250px] h-[320px] sm:h-[380px] flex flex-col justify-between shadow-2xl group ${
                      isActive 
                        ? 'border-amber-400/40 shadow-[0_30px_75px_rgba(0,0,0,0.95),0_0_45px_rgba(217,119,6,0.18)]' 
                        : 'border-white/10 hover:border-white/20'
                    }`}
                  >
                    {/* Card Inner Image Showcase */}
                    <div className="relative w-full h-full rounded-2xl overflow-hidden bg-neutral-950">
                      <img
                        src={cardImg}
                        alt={product.name}
                        className="w-full h-full object-cover object-top pointer-events-none transition-transform duration-700 ease-out group-hover:scale-105"
                        loading="eager"
                      />
                      <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/20 to-transparent pointer-events-none" />

                      {/* Glass Light Shine Ray Sweep on Center Active Card */}
                      {isActive && (
                        <motion.div 
                          initial={{ x: '-100%', opacity: 0 }}
                          animate={{ x: '220%', opacity: [0, 0.4, 0] }}
                          transition={{ repeat: Infinity, duration: 4.2, ease: "easeInOut", repeatDelay: 1.8 }}
                          className="absolute inset-0 w-1/2 bg-gradient-to-r from-transparent via-white/25 to-transparent -skew-x-12 pointer-events-none"
                        />
                      )}

                      {/* Embedded Product Information */}
                      <div className="absolute bottom-0 inset-x-0 p-4 flex flex-col justify-end text-left pointer-events-none">
                        <span className="text-[9px] uppercase tracking-[0.25em] text-neutral-400 font-mono mb-1">
                          {product.subtitle}
                        </span>
                        <h3 className="text-xs sm:text-sm font-normal tracking-tight text-white leading-tight">
                          {product.name}
                        </h3>
                        
                        <div className={`mt-2 text-xs font-mono text-amber-200/90 transition-opacity duration-300 ${
                          isActive ? 'opacity-100' : 'opacity-60'
                        }`}>
                          {product.price}
                        </div>
                      </div>
                    </div>
                  </motion.div>
                );
              })}
            </AnimatePresence>
          </motion.div>
        </div>

        {/* Selected Product Interactive Inspector Panel */}
        <AnimatePresence mode="wait">
          <motion.div 
            key={activeProduct.id}
            initial={{ opacity: 0, y: 25 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.45, ease: "easeOut" }}
            className="mt-6 max-w-4xl mx-auto w-full bg-neutral-900/60 border border-white/10 backdrop-blur-2xl rounded-3xl p-6 sm:p-8 shadow-2xl relative overflow-hidden"
          >
            <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
              
              {/* Left Column: Product Specifications & Details */}
              <div className="space-y-3 flex-1 text-left">
                <div className="flex items-center space-x-3">
                  <span className="text-[10px] uppercase tracking-[0.3em] font-mono text-amber-300/80 bg-amber-500/10 border border-amber-500/20 px-2.5 py-1 rounded-full">
                    {activeProduct.category}
                  </span>
                  <span className="text-[10px] uppercase tracking-[0.25em] font-mono text-neutral-400">
                    {activeProduct.tag}
                  </span>
                </div>

                <h2 className="text-xl sm:text-2xl font-light tracking-tight text-white">
                  {activeProduct.name}
                </h2>

                <p className="text-xs sm:text-sm text-neutral-300 leading-relaxed max-w-2xl font-light">
                  {activeProduct.description}
                </p>

                {/* Technical Specifications Grid */}
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 pt-2 border-t border-white/10 text-xs font-mono text-neutral-400">
                  <div>
                    <div className="text-[9px] uppercase tracking-wider text-neutral-500">Material</div>
                    <div className="text-neutral-200 mt-0.5">{activeProduct.material}</div>
                  </div>
                  <div>
                    <div className="text-[9px] uppercase tracking-wider text-neutral-500">Fit Silhouette</div>
                    <div className="text-neutral-200 mt-0.5">{activeProduct.fit}</div>
                  </div>
                  <div>
                    <div className="text-[9px] uppercase tracking-wider text-neutral-500">Availability</div>
                    <div className="text-amber-200 mt-0.5">{activeProduct.stock}</div>
                  </div>
                </div>
              </div>

              {/* Right Column: Color Swatch Selection & Pricing */}
              <div className="flex flex-col items-start md:items-end justify-between self-stretch md:self-auto border-t md:border-t-0 md:border-l border-white/10 pt-4 md:pt-0 md:pl-8 space-y-4 min-w-[200px]">
                
                {/* Color Palette Selector */}
                <div className="space-y-2 w-full md:text-right">
                  <div className="text-[10px] uppercase tracking-[0.25em] text-neutral-400 font-mono">
                    Palette: <span className="text-amber-200 font-medium">{activeColor.name}</span>
                  </div>

                  <div className="flex items-center space-x-2.5 md:justify-end">
                    {activeProduct.colors.map((c, cIdx) => (
                      <button
                        key={c.name}
                        onClick={() => handleSelectColor(activeProduct.id, cIdx)}
                        className={`group relative w-7 h-7 rounded-full flex items-center justify-center transition-all duration-300 ${
                          activeColorIndex === cIdx
                            ? 'ring-2 ring-amber-300 ring-offset-2 ring-offset-[#030302] scale-110'
                            : 'opacity-70 hover:opacity-100 hover:scale-105'
                        }`}
                        title={c.name}
                      >
                        <span 
                          className="w-full h-full rounded-full border border-white/20 shadow-inner"
                          style={{ backgroundColor: c.hex }}
                        />
                      </button>
                    ))}
                  </div>
                </div>

                {/* Price Display */}
                <div className="md:text-right">
                  <div className="text-[10px] uppercase tracking-[0.25em] text-neutral-500 font-mono">
                    Retail Price
                  </div>
                  <div className="text-2xl font-serif text-amber-100 mt-0.5">
                    {activeProduct.price}
                  </div>
                </div>

              </div>

            </div>
          </motion.div>
        </AnimatePresence>

      </main>

      {/* Clean Ambient Footer */}
      <footer className="relative z-10 py-6 px-8 max-w-7xl mx-auto w-full flex items-center justify-between text-neutral-500 text-[10px] tracking-[0.3em] uppercase">
        <span>SWIPE • SCROLL • CLICK TO REVOLVE TIRE</span>
        <span>FLUXA / 2026</span>
      </footer>

    </div>
  );
}