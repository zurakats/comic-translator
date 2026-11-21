import React, { useState, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Home, History, Settings, Menu, X } from 'lucide-react';

const NAV_ITEMS = [
  { path: '/', label: 'Home', icon: Home },
  { path: '/history', label: 'History', icon: History },
  { path: '/settings', label: 'Settings', icon: Settings },
];

const Navbar = () => {
  const location = useLocation();
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  useEffect(() => {
    setIsMenuOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!isMenuOpen) return;

    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        setIsMenuOpen(false);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isMenuOpen]);

  const getLinkClass = (path, isMobile = false) => {
    const isActive = location.pathname === path;
    const base = isMobile
      ? 'flex items-center gap-3 w-full px-4 py-3 rounded-xl transition-colors duration-300 font-winky tracking-wider text-lg'
      : 'flex items-center gap-2 px-4 lg:px-5 py-2.5 rounded-full transition-colors duration-300 font-winky tracking-wider';

    return `${base} ${
      isActive
        ? 'bg-brand-blue text-white shadow-[0_0_15px_rgba(38,123,250,0.4)]'
        : 'text-white/70 hover:bg-white/10 hover:text-white'
    }`;
  };

  return (
    <>
      <header className="z-[99] fixed top-0 w-full bg-brand-dark md:bg-brand-dark/95 md:backdrop-blur-md border-b border-white/10 shadow-xl h-[80px]">
        <div className="w-full h-full flex items-center justify-between px-4 sm:px-6">
          {/* Left Side: Empty flex space to center the logo on large screens */}
          <div className="hidden lg:block lg:flex-1" />

          {/* Center: Logo */}
          <div className="flex items-center lg:flex-1 lg:justify-center">
            <Link
              to="/"
              onClick={() => setIsMenuOpen(false)}
              className="flex items-center group"
            >
              <p className="logo transition-colors duration-300 group-hover:text-brand-blue drop-shadow-md">
                Comic Translator
              </p>
            </Link>
          </div>

          {/* Right Side: Desktop Navigation Links */}
          <nav className="hidden md:flex items-center justify-end gap-2 lg:gap-4 lg:flex-1">
            {NAV_ITEMS.map(({ path, label, icon: Icon }) => (
              <Link key={path} to={path} className={getLinkClass(path)}>
                <Icon size={20} />
                <span className="text-base lg:text-lg">{label}</span>
              </Link>
            ))}
          </nav>

          {/* Mobile Burger Menu Button */}
          <button
            type="button"
            onClick={() => setIsMenuOpen((prev) => !prev)}
            aria-label={isMenuOpen ? 'Close navigation menu' : 'Open navigation menu'}
            aria-expanded={isMenuOpen}
            aria-controls="mobile-nav-menu"
            className="md:hidden flex items-center justify-center p-2.5 rounded-xl text-white/80 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
          >
            {isMenuOpen ? <X size={26} /> : <Menu size={26} />}
          </button>
        </div>
      </header>

      {/* Mobile Dropdown Navigation */}
      {isMenuOpen && (
        <>
          <div
            className="fixed inset-0 top-[80px] bg-black/70 md:hidden z-[97]"
            onClick={() => setIsMenuOpen(false)}
            aria-hidden="true"
          />
          <nav
            id="mobile-nav-menu"
            aria-label="Mobile navigation"
            className="md:hidden fixed top-[80px] left-0 right-0 z-[98] bg-brand-dark border-b border-white/10 shadow-2xl px-4 py-4"
          >
            <div className="flex flex-col gap-2">
              {NAV_ITEMS.map(({ path, label, icon: Icon }) => (
                <Link
                  key={path}
                  to={path}
                  onClick={() => setIsMenuOpen(false)}
                  className={getLinkClass(path, true)}
                >
                  <Icon size={22} />
                  <span>{label}</span>
                </Link>
              ))}
            </div>
          </nav>
        </>
      )}
    </>
  );
};

export default Navbar;
