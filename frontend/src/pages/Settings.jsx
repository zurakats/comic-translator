import React, { useState, useEffect, useRef } from 'react';
import { Save, Settings2, AlertTriangle, ChevronDown } from 'lucide-react';
import Footer from '../components/Footer';
import { fetchSettings, saveSettings } from '../utils/api';

const Settings = () => {
  const [engine, setEngine] = useState('googletrans');
  const [apiKey, setApiKey] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');
  const savedTimeoutRef = useRef(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const data = await fetchSettings();
        if (cancelled) return;
        setEngine(data.engine || 'googletrans');
        setApiKey(data.apiKey || '');
        setError('');
      } catch (err) {
        if (cancelled) return;
        console.error('Failed to load settings:', err);
        setError('Failed to load settings from server. Please make sure the backend is running.');
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    load();

    return () => {
      cancelled = true;
      if (savedTimeoutRef.current) {
        clearTimeout(savedTimeoutRef.current);
      }
    };
  }, []);

  const handleSave = async () => {
    if (savedTimeoutRef.current) {
      clearTimeout(savedTimeoutRef.current);
      savedTimeoutRef.current = null;
    }

    setIsSaving(true);
    setSaved(false);
    setError('');

    try {
      const res = await saveSettings({
        engine,
        apiKey: apiKey.trim(),
      });
      setEngine(res.engine || engine);
      setApiKey(typeof res.apiKey === 'string' ? res.apiKey : apiKey.trim());
      setSaved(true);
      savedTimeoutRef.current = setTimeout(() => {
        setSaved(false);
        savedTimeoutRef.current = null;
      }, 3000);
    } catch (err) {
      console.error('Failed to save settings:', err);
      setError(err.message || 'Failed to save settings to server.');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <>
      <div className="flex flex-col w-full flex-1 items-center font-winky bg-brand-dark relative py-8 sm:py-10 px-4">
      {/* Background Hero */}
      <div className="absolute inset-0 -z-10 overflow-hidden flex items-center justify-center pointer-events-none opacity-20">
        <img
          src="/assets/hero-banner (2).jpg"
          alt="manga"
          className="object-cover w-full h-full"
        />
        <img
          src="/assets/hero-banner (3).jpg"
          alt="manga"
          className="object-cover w-full h-full"
        />
        <img
          src="/assets/hero-banner (1).jpg"
          alt="manga"
          className="object-cover w-full h-full"
        />
      </div>

      {/* Settings Card */}
      <div className="w-full max-w-[600px] my-auto bg-black/60 backdrop-blur-lg p-6 sm:p-10 rounded-2xl border border-white/10 shadow-2xl flex flex-col gap-6 sm:gap-8 z-10">
        <div className="flex items-center gap-3 border-b border-white/10 pb-4">
          <Settings2 size={28} className="text-brand-blue" />
          <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-wide">
            Settings
          </h1>
        </div>

        <div className="flex flex-col gap-3">
          <label
            htmlFor="translation-engine"
            className="text-lg font-bold text-white/90 tracking-wide"
          >
            Translation Engine
          </label>
          <div className="relative">
            <select
              id="translation-engine"
              value={engine}
              onChange={(e) => setEngine(e.target.value)}
              disabled={isLoading || isSaving}
              className="w-full p-4 pr-12 bg-brand-dark text-white border border-white/20 rounded-xl text-base sm:text-lg focus:outline-none focus:border-brand-blue focus:ring-2 focus:ring-brand-blue/50 transition-all cursor-pointer shadow-inner appearance-none disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <option value="googletrans">
                Google Translate (Free &amp; Default)
              </option>
              <option value="gemini">
                Google Gemini AI (More Natural &amp; Context-Aware)
              </option>
            </select>
            <ChevronDown
              size={20}
              className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 text-white/60"
            />
          </div>
        </div>

        {engine === 'gemini' && (
          <div className="flex flex-col gap-3 animate-in fade-in slide-in-from-top-4 duration-300">
            <label
              htmlFor="gemini-api-key"
              className="text-lg font-bold text-white/90 tracking-wide"
            >
              Google Gemini API Key
            </label>
            <input
              id="gemini-api-key"
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              disabled={isLoading || isSaving}
              placeholder="Enter your API key here..."
              className="p-4 bg-brand-dark text-white border border-white/20 rounded-xl text-base sm:text-lg focus:outline-none focus:border-brand-blue focus:ring-2 focus:ring-brand-blue/50 transition-all placeholder:text-white/30 disabled:opacity-50 disabled:cursor-not-allowed"
            />
            <p className="text-sm text-white/50 mt-1 leading-relaxed">
              Get a free API key at{' '}
              <a
                href="https://aistudio.google.com/"
                target="_blank"
                rel="noreferrer"
                className="text-brand-blue font-bold hover:underline transition-all"
              >
                Google AI Studio
              </a>
              .
            </p>
            <div className="flex items-start gap-2.5 p-3.5 rounded-xl bg-yellow-400/10 border border-yellow-400/20 text-sm text-yellow-300/90 leading-relaxed mt-1">
              <AlertTriangle
                size={18}
                className="shrink-0 mt-0.5 text-yellow-400"
              />
              <p>
                Comics with many pages or heavy text may take a little longer to
                process, as the system automatically paces and retries requests
                to avoid hitting API rate limits.
              </p>
            </div>
          </div>
        )}

        <button
          type="button"
          onClick={handleSave}
          disabled={isLoading || isSaving}
          className="mt-2 flex items-center justify-center gap-3 w-full py-4 bg-brand-blue text-white text-base sm:text-lg font-bold tracking-widest rounded-xl hover:bg-brand-blue-hover transition-all duration-300 shadow-[0_4px_14px_rgba(38,123,250,0.3)] hover:shadow-[0_6px_20px_rgba(38,123,250,0.4)] cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Save size={22} />
          {isLoading ? 'LOADING...' : isSaving ? 'SAVING...' : 'SAVE SETTINGS'}
        </button>

        {error && (
          <p className="text-red-400 text-center font-semibold text-sm tracking-wide">
            {error}
          </p>
        )}

        {saved && (
          <p className="text-green-400 text-center font-bold text-sm tracking-widest animate-pulse">
            SETTINGS SAVED SUCCESSFULLY!
          </p>
        )}
      </div>
      </div>
      <Footer />
    </>
  );
};

export default Settings;
