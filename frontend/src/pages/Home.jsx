import React, { useState, useRef, useEffect } from 'react';
import { Download, Upload, RefreshCw } from 'lucide-react';
import ComicBatchViewer from '../components/ComicBatchViewer';
import Footer from '../components/Footer';
import { fetchSettings, processImages } from '../utils/api';

const Home = () => {
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [sourceLang, setSourceLang] = useState('');
  const [targetLang, setTargetLang] = useState('');
  const [statusText, setStatusText] = useState('Upload comic pages to get started');
  const [statusColor, setStatusColor] = useState('rgba(0, 0, 0, 0.6)');
  const [isProcessing, setIsProcessing] = useState(false);
  const [results, setResults] = useState([]);
  const [resultBatchKey, setResultBatchKey] = useState(0);

  const timerRef = useRef(null);
  const startTimeRef = useRef(null);

  const stopTimer = () => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  };

  useEffect(() => {
    return () => stopTimer();
  }, []);

  const startTimer = () => {
    if (!timerRef.current) {
      startTimeRef.current = Date.now();
      timerRef.current = setInterval(() => {
        const elapsed = Math.floor((Date.now() - startTimeRef.current) / 1000);
        setStatusText(`Processing images: ${elapsed}s`);
      }, 1000);
    }
  };

  const handleUpload = (e) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      const fileArray = Array.from(files);
      setSelectedFiles(fileArray);
      setStatusText(
        `${fileArray.length} ${fileArray.length === 1 ? 'image' : 'images'} selected`
      );
      setStatusColor('rgba(0, 0, 0, 0.6)');
      setResults([]);
    }
    e.target.value = null;
  };

  const translateImage = async () => {
    if (selectedFiles.length === 0) {
      alert('Please upload at least one image before translating.');
      return;
    }
    if (!sourceLang || !targetLang) {
      alert('Please select both a source language and a target language.');
      return;
    }

    setIsProcessing(true);
    setStatusColor('rgba(0, 0, 0, 0.6)');
    setStatusText('Loading settings...');

    try {
      const currentSettings = await fetchSettings();
      const engine = currentSettings?.engine || 'googletrans';
      const apiKey = (currentSettings?.apiKey || '').trim();

      if (engine === 'gemini' && !apiKey) {
        setStatusText(
          `${selectedFiles.length} ${selectedFiles.length === 1 ? 'image' : 'images'} selected`
        );
        alert('Gemini API key is not set. Please configure it in Settings.');
        return;
      }

      startTimer();
      setStatusText('Processing...');

      const formData = new FormData();
      selectedFiles.forEach((file) => {
        formData.append('image[]', file);
      });
      formData.append('source', sourceLang);
      formData.append('target', targetLang);
      formData.append('engine', engine);
      formData.append('apiKey', apiKey);

      const data = await processImages(formData);

      if (!data.results || data.results.length === 0) {
        throw new Error('Translation returned no results.');
      }

      setResults(data.results);
      setResultBatchKey((prev) => prev + 1);

      const elapsedSeconds = Math.floor((Date.now() - startTimeRef.current) / 1000);
      stopTimer();
      setStatusText(`Translation complete!\nTime elapsed: ${elapsedSeconds}s`);
      setStatusColor('rgba(0, 128, 0, 0.6)');
    } catch (err) {
      stopTimer();
      setStatusText('An error occurred!');
      setStatusColor('rgba(255, 0, 0, 0.6)');
      alert(
        'Failed to process images. Please make sure the backend server is running and your API key is valid.'
      );
      console.error(err);
    } finally {
      setIsProcessing(false);
    }
  };

  const downloadPDF = async () => {
    const imageUrls = results.map((r) => r.translated).filter(Boolean);
    if (!imageUrls || imageUrls.length === 0) {
      alert('No translated images available to download.');
      return;
    }

    const { jsPDF } = await import('jspdf');
    const pdf = new jsPDF();
    const promises = imageUrls.map((url) => {
      return new Promise((resolve) => {
        const img = new Image();
        img.crossOrigin = 'anonymous';
        img.src = url;
        img.onload = () => resolve(img);
        img.onerror = () => resolve(null);
      });
    });

    const images = await Promise.all(promises);
    images.forEach((img, index) => {
      if (!img) return;
      const pageWidth = pdf.internal.pageSize.getWidth();
      const pageHeight = pdf.internal.pageSize.getHeight();

      const ratio = Math.min(pageWidth / img.width, pageHeight / img.height);
      const w = img.width * ratio;
      const h = img.height * ratio;

      const x = (pageWidth - w) / 2;
      const y = (pageHeight - h) / 2;

      if (index > 0) pdf.addPage();
      pdf.addImage(img, 'JPEG', x, y, w, h);
    });

    pdf.save('translated_comic.pdf');
  };

  return (
    <>
      <div className="flex flex-col w-full min-h-[calc(100dvh-80px)] shrink-0 justify-center items-center z-10 relative px-4 py-6 sm:px-6 md:py-10 font-winky">
        <div className="w-full max-w-[420px] flex flex-col items-center gap-4 bg-[#141414]/88 border border-white/15 rounded-2xl p-5 shadow-2xl md:max-w-none md:w-auto md:bg-transparent md:border-0 md:rounded-none md:p-0 md:shadow-none md:gap-5">
          <div
            id="imageInfo"
            role="status"
            aria-live="polite"
            className="w-full md:w-[400px] text-white text-center text-sm sm:text-base md:text-[18px] leading-snug rounded-xl md:rounded-lg border border-white/10 md:border-0 px-4 py-2.5 md:px-6 md:py-3 md:mb-3 z-10"
            style={{ backgroundColor: statusColor, whiteSpace: 'pre-line' }}
          >
            {statusText}
          </div>

          <input
            type="file"
            id="imageInput"
            accept="image/*"
            style={{ display: 'none' }}
            multiple
            onChange={handleUpload}
            disabled={isProcessing}
          />

          <label
            htmlFor="imageInput"
            className="w-full md:w-[400px] h-[56px] sm:h-[60px] md:h-[71px] flex gap-2.5 items-center justify-center bg-brand-dark text-xl sm:text-2xl md:text-[28px] border-2 border-white/25 md:border-[3px] md:border-brand-dark rounded-xl md:rounded-[5px] text-white transition-colors duration-300 ease-out hover:bg-white hover:text-brand-dark active:scale-[0.99] cursor-pointer text-center leading-none md:mt-2 shadow-lg"
            style={{
              pointerEvents: isProcessing ? 'none' : 'auto',
              opacity: isProcessing ? 0.5 : 1,
            }}
          >
            <Upload className="w-5 h-5 sm:w-6 sm:h-6 shrink-0" />
            <span>UPLOAD IMAGES</span>
          </label>

          <div className="w-full md:w-auto flex flex-col md:flex-row gap-2.5 md:gap-[15px] items-center justify-center md:my-[10px]">
            <select
              id="source-lang"
              aria-label="Source language"
              value={sourceLang}
              onChange={(e) => setSourceLang(e.target.value)}
              disabled={isProcessing}
              className="h-[50px] md:h-[55px] w-full md:w-[250px] px-4 text-base md:text-[18px] bg-white border-2 border-brand-blue rounded-xl md:rounded-[10px] shadow-sm text-brand-dark focus:outline-none focus:border-brand-blue-hover focus:ring-4 focus:ring-brand-blue/20 transition-[border-color,box-shadow] duration-300 disabled:opacity-50 cursor-pointer hover:shadow-md"
            >
              <option value="">- Source Language -</option>
              <option value="jp">Japanese</option>
              <option value="ko">Korean</option>
              <option value="ch_sim">Chinese (Simplified)</option>
              <option value="en">English</option>
            </select>

            <div className="w-full md:w-auto flex items-center justify-center gap-3 md:gap-0">
              <span className="h-px flex-1 bg-white/15 md:hidden" aria-hidden="true" />
              <div className="flex items-center justify-center w-8 h-8 md:w-[40px] md:h-[40px] bg-brand-blue text-white rounded-full shadow-md rotate-90 md:rotate-0 transition-transform hover:scale-110 shrink-0">
                <RefreshCw className="w-4 h-4 md:w-5 md:h-5" />
              </div>
              <span className="h-px flex-1 bg-white/15 md:hidden" aria-hidden="true" />
            </div>

            <select
              id="target-lang"
              aria-label="Target language"
              value={targetLang}
              onChange={(e) => setTargetLang(e.target.value)}
              disabled={isProcessing}
              className="h-[50px] md:h-[55px] w-full md:w-[250px] px-4 text-base md:text-[18px] bg-white border-2 border-brand-blue rounded-xl md:rounded-[10px] shadow-sm text-brand-dark focus:outline-none focus:border-brand-blue-hover focus:ring-4 focus:ring-brand-blue/20 transition-[border-color,box-shadow] duration-300 disabled:opacity-50 cursor-pointer hover:shadow-md"
            >
              <option value="">- Target Language -</option>
              <option value="id">Indonesian</option>
              <option value="en">English</option>
            </select>
          </div>

          <button
            type="button"
            id="button-translate"
            onClick={translateImage}
            disabled={isProcessing}
            className="w-full md:w-[220px] h-[52px] md:h-[53px] mt-1 md:mt-0 text-lg md:text-[18px] tracking-wide bg-brand-blue border-2 border-brand-blue rounded-xl md:rounded-[5px] shadow-[0_6px_18px_rgba(38,123,250,0.3)] md:shadow-[4px_4px_4px_rgba(0,0,0,0.3)] cursor-pointer text-white transition-[background-color,color,border-color,transform] duration-300 ease-out hover:bg-white hover:text-brand-blue-hover hover:border-brand-blue active:scale-[0.99] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isProcessing ? 'Processing...' : 'Translate'}
          </button>
        </div>
      </div>

      {/* Hero Background */}
      <div className="hero">
        <img src="/assets/hero-banner (2).jpg" alt="manga page 2" decoding="async" className="hidden md:block" />
        <img src="/assets/hero-banner (3).jpg" alt="manga page 3" decoding="async" fetchPriority="high" />
        <img src="/assets/hero-banner (1).jpg" alt="manga page 1" decoding="async" className="hidden md:block" />
      </div>

      {/* Results Section */}
      {results.length > 0 && (
        <>
          <section className="bg-brand-dark w-full pt-3 pb-0 px-0 lg:py-8 lg:px-4 flex flex-col items-center justify-center shadow-inner z-20 relative border-t border-white/10">
            <div className="w-full max-w-[1600px]">
              <ComicBatchViewer
                key={resultBatchKey}
                images={results}
                stickyTopClass="top-[88px]"
                headerAction={
                  <button
                    type="button"
                    id="downloadPdfBtn"
                    onClick={downloadPDF}
                    disabled={isProcessing}
                    className="inline-flex items-center justify-center gap-2 min-h-[44px] px-5 py-2.5 md:min-h-0 md:px-4 md:py-2 text-sm font-semibold tracking-wide bg-black/70 text-white border border-white/20 rounded-xl md:rounded-lg shadow-md cursor-pointer transition-colors duration-200 hover:bg-brand-blue hover:border-brand-blue active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <Download size={16} />
                    <span>Download PDF</span>
                  </button>
                }
              />
            </div>
          </section>
          <Footer />
        </>
      )}
    </>
  );
};

export default Home;
