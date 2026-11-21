import React, { memo, useState } from 'react';

const ComicBatchViewer = memo(({
  images,
  stickyTopClass = 'top-[88px]',
  defaultView = 'translated',
  headerAction = null,
}) => {
  const [activeView, setActiveView] = useState(defaultView);

  if (!images || images.length === 0) {
    return null;
  }

  const getToggleButtonClass = (view) => {
    const isActive = activeView === view;
    return `px-5 py-2 rounded-full text-sm sm:text-base font-bold tracking-wide transition-colors cursor-pointer ${isActive
        ? 'bg-brand-blue text-white shadow-[0_0_12px_rgba(38,123,250,0.45)]'
        : 'text-white/70 hover:text-white'
      }`;
  };

  return (
    <div className="w-full">
      {/* Mobile / Tablet Sticky View Switcher */}
      <div
        className={`lg:hidden sticky ${stickyTopClass} z-30 flex justify-center py-2 mb-2 pointer-events-none`}
      >
        <div className="inline-flex items-center bg-black/95 p-1.5 rounded-full border border-white/15 shadow-2xl pointer-events-auto">
          <button
            type="button"
            aria-pressed={activeView === 'original'}
            onClick={() => setActiveView('original')}
            className={getToggleButtonClass('original')}
          >
            Original
          </button>
          <button
            type="button"
            aria-pressed={activeView === 'translated'}
            onClick={() => setActiveView('translated')}
            className={getToggleButtonClass('translated')}
          >
            Translated
          </button>
        </div>
      </div>

      {headerAction && (
        <div className="flex justify-center mb-3">{headerAction}</div>
      )}

      {/* Batch Containers: Edge-to-Edge Digital Reader on Mobile, Side-by-Side on Desktop */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-0 lg:gap-6 xl:gap-8 items-start w-full">
        {/* Original Batch Container */}
        <div
          className={`${
            activeView === 'original' ? 'flex' : 'hidden'
          } lg:flex w-full p-0 m-0 bg-black lg:rounded-xl lg:border lg:border-white/10 lg:overflow-hidden flex-col gap-0 shadow-lg [contain:layout_style]`}
        >
          <p className="text-white text-center text-base sm:text-lg font-bold tracking-wide py-2.5 m-0">
            Original
          </p>
          <div className="flex flex-col gap-0 p-0 m-0">
            {images.map((item, index) => (
              <img
                key={item.original || index}
                src={item.original}
                alt={`Original page ${index + 1}`}
                loading={activeView === 'original' && index < 2 ? 'eager' : 'lazy'}
                decoding="async"
                className="block w-full h-auto object-contain m-0 p-0"
              />
            ))}
          </div>
        </div>

        {/* Translated Batch Container */}
        <div
          className={`${
            activeView === 'translated' ? 'flex' : 'hidden'
          } lg:flex w-full p-0 m-0 bg-black lg:rounded-xl lg:border lg:border-white/10 lg:overflow-hidden flex-col gap-0 shadow-lg [contain:layout_style]`}
        >
          <p className="text-brand-blue text-center text-base sm:text-lg font-bold tracking-wide py-2.5 m-0">
            Translated
          </p>
          <div className="flex flex-col gap-0 p-0 m-0">
            {images.map((item, index) =>
              item.translated ? (
                <img
                  key={item.translated || index}
                  src={item.translated}
                  alt={`Translated page ${index + 1}`}
                  loading={activeView === 'translated' && index < 2 ? 'eager' : 'lazy'}
                  decoding="async"
                  className="block w-full h-auto object-contain m-0 p-0"
                />
              ) : null
            )}
          </div>
        </div>
      </div>
    </div>
  );
});

export default ComicBatchViewer;
