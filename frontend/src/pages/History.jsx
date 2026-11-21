import React, { useState, useEffect } from 'react';
import { Trash2, LayoutGrid, List, X, Pencil, Check } from 'lucide-react';
import ComicBatchViewer from '../components/ComicBatchViewer';
import Footer from '../components/Footer';
import {
  fetchHistory,
  renameHistoryBatch,
  deleteHistoryBatch,
  clearAllHistory,
} from '../utils/api';

const LANG_CODE_MAP = {
  jp: 'JP',
  ko: 'KO',
  ch_sim: 'ZH',
  ch_tra: 'ZH',
  en: 'EN',
  id: 'ID',
};

const formatLangCode = (code) =>
  LANG_CODE_MAP[code] || (code || '').toUpperCase();

const History = () => {
  const [history, setHistory] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [viewMode, setViewMode] = useState('grid'); // 'grid' | 'list'
  const [selectedItem, setSelectedItem] = useState(null);
  const [editingTarget, setEditingTarget] = useState(null); // { id: string, scope: 'card' | 'modal' }
  const [draftName, setDraftName] = useState('');

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const data = await fetchHistory();
        if (cancelled) return;
        setHistory(data);
        setError('');
      } catch (err) {
        if (cancelled) return;
        console.error('Failed to fetch history:', err);
        setError('Failed to load translation history from server.');
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedItem) return;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        if (editingTarget?.scope === 'modal') {
          setEditingTarget(null);
          setDraftName('');
        } else {
          setSelectedItem(null);
          setEditingTarget(null);
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [selectedItem, editingTarget]);

  const getBatchName = (item) => item?.name || '';

  const startEditing = (item, scope, e) => {
    e?.stopPropagation();
    setEditingTarget({ id: String(item.id), scope });
    setDraftName(item.name || '');
  };

  const cancelEditing = (e) => {
    e?.stopPropagation();
    setEditingTarget(null);
    setDraftName('');
  };

  const commitBatchName = async (id, e) => {
    e?.preventDefault();
    e?.stopPropagation();

    const trimmed = draftName.trim().slice(0, 80);

    try {
      const res = await renameHistoryBatch(id, trimmed);
      const savedName = typeof res?.name === 'string' ? res.name : trimmed;

      setHistory((prev) =>
        prev.map((entry) =>
          entry.id === id ? { ...entry, name: savedName } : entry
        )
      );
      setSelectedItem((prev) =>
        prev && prev.id === id ? { ...prev, name: savedName } : prev
      );
      setEditingTarget(null);
      setDraftName('');
    } catch (err) {
      console.error('Failed to rename batch:', err);
      alert('Failed to rename batch. Please make sure the backend server is running.');
    }
  };

  const clearHistory = async () => {
    if (window.confirm('Are you sure you want to delete all translation history?')) {
      try {
        await clearAllHistory();
        setHistory([]);
        setSelectedItem(null);
        setEditingTarget(null);
        setDraftName('');
      } catch (err) {
        console.error('Failed to clear history:', err);
        alert('Failed to clear history. Please make sure the backend server is running.');
      }
    }
  };

  const deleteBatch = async (item, e) => {
    e?.stopPropagation();
    const label = getBatchName(item) || 'Untitled Batch';
    if (!window.confirm(`Are you sure you want to delete "${label}"?`)) {
      return;
    }

    try {
      await deleteHistoryBatch(item.id);
      setHistory((prev) => prev.filter((entry) => entry.id !== item.id));

      if (selectedItem?.id === item.id) {
        setSelectedItem(null);
      }
      if (editingTarget?.id === String(item.id)) {
        setEditingTarget(null);
        setDraftName('');
      }
    } catch (err) {
      console.error('Failed to delete batch:', err);
      alert('Failed to delete batch. Please make sure the backend server is running.');
    }
  };

  const openModal = (item) => {
    setSelectedItem(item);
    setEditingTarget(null);
    setDraftName('');
  };

  const closeModal = () => {
    setSelectedItem(null);
    setEditingTarget(null);
    setDraftName('');
  };

  const renderNameEditor = (id, inputClassName = '') => (
    <form
      onSubmit={(e) => commitBatchName(id, e)}
      onClick={(e) => e.stopPropagation()}
      className="flex items-center gap-1.5 w-full min-w-0"
    >
      <input
        type="text"
        value={draftName}
        onChange={(e) => setDraftName(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Escape') {
            e.stopPropagation();
            cancelEditing(e);
          }
        }}
        placeholder="Enter batch name..."
        maxLength={80}
        autoFocus
        aria-label="Batch name"
        className={`flex-1 min-w-0 px-2.5 py-1 rounded-lg bg-brand-dark text-white text-sm sm:text-base border border-brand-blue focus:outline-none focus:ring-2 focus:ring-brand-blue/40 placeholder:text-white/30 ${inputClassName}`}
      />
      <button
        type="submit"
        aria-label="Save batch name"
        title="Save batch name"
        className="p-1.5 rounded-lg bg-brand-blue text-white hover:bg-brand-blue-hover transition-colors shrink-0 cursor-pointer"
      >
        <Check size={16} />
      </button>
      <button
        type="button"
        onClick={cancelEditing}
        aria-label="Cancel renaming"
        title="Cancel"
        className="p-1.5 rounded-lg bg-white/10 text-white/80 hover:bg-white/20 hover:text-white transition-colors shrink-0 cursor-pointer"
      >
        <X size={16} />
      </button>
    </form>
  );

  return (
    <>
      <div className="flex flex-col w-full flex-1 items-center font-winky bg-brand-dark relative py-8 sm:py-10">
      {/* Dashboard Header */}
      <div className="w-full max-w-[1200px] px-4 sm:px-6 flex flex-col md:flex-row justify-between items-center mb-8 gap-4 z-10">
        <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-widest drop-shadow-md text-center md:text-left">
          TRANSLATION HISTORY
        </h1>

        <div className="flex items-center gap-3 sm:gap-4">
          <div className="flex items-center bg-black/40 rounded-lg p-1 border border-white/10">
            <button
              type="button"
              onClick={() => setViewMode('grid')}
              aria-label="Grid view"
              title="Grid view"
              className={`p-2 rounded transition-colors cursor-pointer ${
                viewMode === 'grid'
                  ? 'bg-brand-blue text-white'
                  : 'text-white/50 hover:text-white'
              }`}
            >
              <LayoutGrid size={20} />
            </button>
            <button
              type="button"
              onClick={() => setViewMode('list')}
              aria-label="List view"
              title="List view"
              className={`p-2 rounded transition-colors cursor-pointer ${
                viewMode === 'list'
                  ? 'bg-brand-blue text-white'
                  : 'text-white/50 hover:text-white'
              }`}
            >
              <List size={20} />
            </button>
          </div>

          {history.length > 0 && (
            <button
              type="button"
              onClick={clearHistory}
              aria-label="Clear all history"
              className="flex items-center gap-2 px-4 py-2 bg-red-600/90 text-white rounded-lg hover:bg-red-500 transition-colors shadow-lg text-sm sm:text-base cursor-pointer"
            >
              <Trash2 size={18} />
              <span>Clear All</span>
            </button>
          )}
        </div>
      </div>

      {/* History Content */}
      {isLoading ? (
        <div className="flex-1 flex items-center justify-center z-10 px-4">
          <p className="text-xl text-white/60 tracking-wider text-center">
            Loading translation history...
          </p>
        </div>
      ) : error ? (
        <div className="flex-1 flex items-center justify-center z-10 px-4">
          <p className="text-xl text-red-400 tracking-wider text-center">
            {error}
          </p>
        </div>
      ) : history.length === 0 ? (
        <div className="flex-1 flex items-center justify-center z-10 px-4">
          <p className="text-xl text-white/40 tracking-wider text-center">
            No translation history yet.
          </p>
        </div>
      ) : (
        <div
          className={`w-full max-w-[1200px] px-4 sm:px-6 z-10 ${
            viewMode === 'grid'
              ? 'grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6'
              : 'flex flex-col gap-4'
          }`}
        >
          {history.map((item) => {
            const customName = getBatchName(item);
            const isEditingCard =
              editingTarget?.scope === 'card' &&
              editingTarget.id === String(item.id);
            const pageCount = item.images.length;

            return (
              <div
                key={item.id}
                onClick={() => openModal(item)}
                className={`bg-black/70 md:bg-black/60 md:backdrop-blur-md rounded-xl border border-white/10 cursor-pointer group hover:border-brand-blue hover:shadow-[0_0_20px_rgba(38,123,250,0.2)] transition-[border-color,box-shadow] overflow-hidden [contain:layout_style_paint] ${
                  viewMode === 'list'
                    ? 'flex flex-row items-stretch min-h-[120px]'
                    : 'flex flex-col'
                }`}
              >
                {/* Thumbnail */}
                <div
                  className={`${
                    viewMode === 'list'
                      ? 'w-[100px] sm:w-[130px] self-stretch border-r border-white/5'
                      : 'w-full h-[170px] border-b border-white/5'
                  } bg-black/80 flex-shrink-0 relative overflow-hidden`}
                >
                  <img
                    src={item.images[0]?.original}
                    alt={customName || 'Batch thumbnail'}
                    loading="lazy"
                    decoding="async"
                    className="w-full h-full object-cover opacity-80 group-hover:opacity-100 md:group-hover:scale-105 transition-opacity duration-300 md:transition-[opacity,transform] md:duration-500"
                  />
                </div>

                {/* Info */}
                <div className="p-3.5 sm:p-4 flex flex-col justify-between gap-2 flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2 min-h-[32px]">
                    {isEditingCard ? (
                      renderNameEditor(item.id)
                    ) : (
                      <>
                        <h2
                          className={
                            customName
                              ? 'text-base sm:text-lg font-bold text-white truncate'
                              : 'text-base sm:text-lg font-medium text-white/50 italic truncate'
                          }
                          title={customName || 'Untitled Batch'}
                        >
                          {customName || 'Untitled Batch'}
                        </h2>
                        <div className="flex items-center gap-1 shrink-0">
                          <button
                            type="button"
                            onClick={(e) => startEditing(item, 'card', e)}
                            aria-label="Rename batch"
                            title="Rename batch"
                            className="p-1.5 rounded-lg bg-white/5 text-white/70 hover:text-white hover:bg-brand-blue/80 transition-colors cursor-pointer"
                          >
                            <Pencil size={15} />
                          </button>
                          <button
                            type="button"
                            onClick={(e) => deleteBatch(item, e)}
                            aria-label="Delete batch"
                            title="Delete batch"
                            className="p-1.5 rounded-lg bg-white/5 text-white/70 hover:text-white hover:bg-red-600 transition-colors cursor-pointer"
                          >
                            <Trash2 size={15} />
                          </button>
                        </div>
                      </>
                    )}
                  </div>

                  <p className="text-xs text-brand-blue font-semibold">
                    {item.date}
                  </p>

                  <div className="flex items-center justify-between gap-2 pt-1">
                    <p className="text-xs text-white/60 truncate">
                      <span className="uppercase text-white">{item.engine}</span> |{' '}
                      {formatLangCode(item.sourceLang)} &rarr;{' '}
                      {formatLangCode(item.targetLang)}
                    </p>
                    <span className="text-xs bg-white/10 text-white px-2.5 py-0.5 rounded-full shrink-0">
                      {pageCount} {pageCount === 1 ? 'Page' : 'Pages'}
                    </span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Floating Modal for Reading */}
      {selectedItem && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Batch viewer"
          className="fixed inset-0 z-[100] bg-black/95 flex flex-col items-center p-0"
        >
          {/* Modal Top Bar */}
          <div className="w-full max-w-[1400px] flex items-start sm:items-center justify-between gap-3 px-4 py-3 sm:px-6 sm:py-4 border-b border-white/10 shrink-0">
            <div className="flex flex-col gap-1 min-w-0 flex-1">
              {editingTarget?.scope === 'modal' &&
              editingTarget.id === String(selectedItem.id) ? (
                <div className="max-w-[440px]">
                  {renderNameEditor(selectedItem.id, 'sm:text-lg py-1.5')}
                </div>
              ) : (
                <div className="flex items-center gap-2 min-w-0">
                  <h2
                    className={`text-lg sm:text-2xl font-bold truncate ${
                      getBatchName(selectedItem)
                        ? 'text-white'
                        : 'text-white/60 italic'
                    }`}
                  >
                    {getBatchName(selectedItem) || 'Untitled Batch'}
                  </h2>
                  <button
                    type="button"
                    onClick={(e) => startEditing(selectedItem, 'modal', e)}
                    aria-label="Rename batch"
                    title="Rename batch"
                    className="p-1.5 rounded-lg bg-white/10 text-white/75 hover:text-white hover:bg-brand-blue transition-colors shrink-0 cursor-pointer"
                  >
                    <Pencil size={16} />
                  </button>
                </div>
              )}

              <p className="text-xs sm:text-sm text-white/60 flex flex-wrap items-center gap-x-2 gap-y-0.5">
                <span>{selectedItem.date}</span>
                <span>&bull;</span>
                <span className="uppercase">{selectedItem.engine}</span>
                <span>&bull;</span>
                <span>
                  {formatLangCode(selectedItem.sourceLang)} &rarr;{' '}
                  {formatLangCode(selectedItem.targetLang)}
                </span>
                <span>&bull;</span>
                <span>
                  {selectedItem.images.length}{' '}
                  {selectedItem.images.length === 1 ? 'Page' : 'Pages'}
                </span>
              </p>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              <button
                type="button"
                onClick={(e) => deleteBatch(selectedItem, e)}
                aria-label="Delete batch"
                title="Delete batch"
                className="p-2 bg-white/10 hover:bg-red-600 text-white rounded-full transition-colors cursor-pointer"
              >
                <Trash2 size={20} />
              </button>
              <button
                type="button"
                onClick={closeModal}
                aria-label="Close viewer"
                title="Close"
                className="p-2 bg-white/10 hover:bg-red-500 text-white rounded-full transition-colors cursor-pointer"
              >
                <X size={24} />
              </button>
            </div>
          </div>

          {/* Scrollable Batch Viewer Body */}
          <div className="w-full max-w-[1400px] flex-1 overflow-y-auto overscroll-contain p-0 lg:px-4 lg:py-4">
            <ComicBatchViewer
              key={selectedItem.id}
              images={selectedItem.images}
              stickyTopClass="top-0"
            />
          </div>
        </div>
      )}
      </div>
      <Footer />
    </>
  );
};

export default History;
