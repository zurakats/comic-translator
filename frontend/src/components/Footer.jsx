import React from 'react';

const Footer = () => {
  return (
    <footer className="w-full bg-brand-dark/95 border-t border-white/10 relative z-20 mt-auto">
      <div className="max-w-[1200px] mx-auto px-6 py-5 flex flex-col sm:flex-row items-center justify-between gap-2 text-center sm:text-left">
        <p className="text-sm text-white/80">
          Built by <span className="text-brand-blue font-bold">zurakats</span>
        </p>
        <p className="text-xs sm:text-sm text-white/50">
          Built using React, Flask, YOLOv5, Manga-OCR, EasyOCR, &amp; more.
        </p>
      </div>
    </footer>
  );
};

export default Footer;
