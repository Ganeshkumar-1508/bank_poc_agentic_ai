/**
 * Enhanced Markdown Renderer for CrewAI Outputs
 * 
 * This module provides enhanced Markdown rendering with:
 * - Preloaded marked.js for reliable async rendering
 * - Syntax highlighting via highlight.js
 * - GFM tables support
 * - Error handling and fallbacks
 * - Product-specific styling support
 * 
 * Usage:
 * // Load and render
 * const html = await renderMarkdown(markdownText);
 * document.getElementById('result').innerHTML = html;
 * 
 * // With element target and syntax highlighting
 * await renderMarkdownToElement(markdownText, '#result');
 * 
 * // Safe rendering with error handling
 * const html = renderMarkdownSafe(markdownText);
 */

(function (global) {
  "use strict";

  let marked = null;
  let hljs = null;

  /**
   * Preload marked.js immediately when script loads
   * This ensures marked.js is available before any rendering is attempted
   */
  (function preloadMarked() {
    if (typeof marked === "undefined") {
      var script = document.createElement("script");
      script.src = "https://cdn.jsdelivr.net/npm/marked/marked.min.js";
      script.onload = function () {
        console.log("marked.js preloaded successfully");
        marked = window.marked;
      };
      script.onerror = function () {
        console.error("Failed to load marked.js from CDN");
      };
      document.head.appendChild(script);
    }
  })();

  /**
   * Load highlight.js for syntax highlighting
   * @returns {Promise} Resolves when highlight.js is loaded
   */
  function loadHighlightJS() {
    return new Promise((resolve, reject) => {
      if (typeof hljs !== "undefined" && hljs) {
        resolve(hljs);
        return;
      }

      if (typeof window.hljs !== "undefined") {
        hljs = window.hljs;
        resolve(hljs);
        return;
      }

      // Load highlight.js script
      const highlightScript = document.createElement("script");
      highlightScript.src = "https://cdn.jsdelivr.net/npm/highlight.js@11/lib/highlight.min.js";
      highlightScript.onload = () => {
        hljs = window.hljs;
        console.log("highlight.js loaded");
        resolve(hljs);
      };
      highlightScript.onerror = () => {
        console.error("Failed to load highlight.js from CDN");
        resolve(null); // Continue without syntax highlighting
      };
      document.head.appendChild(highlightScript);

      // Load highlight.js style
      const highlightStyle = document.createElement("link");
      highlightStyle.rel = "stylesheet";
      highlightStyle.href = "https://cdn.jsdelivr.net/npm/highlight.js@11/styles/github-dark.min.css";
      highlightStyle.onerror = () => {
        console.warn("Failed to load highlight.js style");
      };
      document.head.appendChild(highlightStyle);
    });
  }

  /**
   * Load marked.js from CDN if not already available
   * @returns {Promise} Resolves when marked.js is loaded
   */
  function loadMarked() {
    return new Promise((resolve, reject) => {
      if (typeof marked !== "undefined" && marked) {
        resolve(marked);
        return;
      }

      if (typeof window.marked !== "undefined") {
        marked = window.marked;
        resolve(marked);
        return;
      }

      const script = document.createElement("script");
      script.src = "https://cdn.jsdelivr.net/npm/marked/marked.min.js";
      script.onload = () => {
        marked = window.marked;
        console.log("marked.js loaded on demand");
        resolve(marked);
      };
      script.onerror = () => {
        reject(new Error("Failed to load marked.js from CDN"));
      };
      document.head.appendChild(script);
    });
  }

  /**
   * Configure marked with custom options and extensions
   */
  function configureMarked() {
    if (!marked) return;

    // Enable GFM features
    marked.use({
      breaks: true,
      gfm: true,
      headerIds: false,
      mangle: false
    });

    // Configure syntax highlighting
    if (typeof hljs !== "undefined" && hljs) {
      marked.setOptions({
        highlight: function (code, lang) {
          if (lang && hljs.getLanguage(lang)) {
            try {
              return hljs.highlight(code, { language: lang }).value;
            } catch (err) {
              console.warn(`Syntax highlighting failed for language: ${lang}`, err);
            }
          }
          return hljs.highlightAuto(code).value;
        }
      });
    }
  }

  /**
   * Escape HTML special characters
   * @param {string} text - Text to escape
   * @returns {string} - Escaped text
   */
  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  /**
   * Render Markdown to HTML with error handling
   * @param {string} markdown - The markdown text to render
   * @returns {string} - The rendered HTML (synchronous, safe to use)
   */
  function renderMarkdownSafe(markdown) {
    if (!markdown || typeof markdown !== "string") {
      return "<p>No content to display</p>";
    }

    try {
      // Check if marked is available
      if (typeof marked === "undefined" || !marked) {
        // Fallback: escape HTML and show as preformatted text
        console.warn("marked.js not available, using fallback rendering");
        return (
          '<pre style="white-space: pre-wrap; background: #1a1a2e; padding: 1em; border-radius: 6px; color: #e0e0e0;">' +
          escapeHtml(markdown) +
          "</pre>"
        );
      }

      // Configure marked if not already configured
      configureMarked();

      // Render markdown
      const html = marked.parse(markdown);
      return html;
    } catch (error) {
      console.error("Markdown rendering error:", error);
      return (
        '<div class="error">' +
        "Failed to render content. Please try again." +
        "</div>"
      );
    }
  }

  /**
   * Render Markdown to HTML (async version for compatibility)
   * @param {string} markdown - The markdown text to render
   * @returns {Promise<string>} - The rendered HTML
   */
  async function renderMarkdown(markdown) {
    if (!markdown || typeof markdown !== "string") {
      return "<p>No content to display</p>";
    }

    try {
      // Load marked.js if not available
      if (!marked) {
        await loadMarked();
      }

      // Configure marked
      configureMarked();

      // Render markdown
      const html = marked ? marked.parse(markdown) : markdown;
      return html;
    } catch (error) {
      console.error("Error rendering markdown:", error);
      // Return escaped markdown as fallback
      return "<pre style='white-space: pre-wrap; background: #1a1a2e; padding: 1em; border-radius: 6px; color: #e0e0e0;'>" + escapeHtml(markdown) + "</pre>";
    }
  }

  /**
   * Ensure marked.js is loaded
   * @returns {Promise} Resolves when marked is available
   */
  async function ensureMarkedLoaded() {
    if (marked) {
      return marked;
    }
    return await loadMarked();
  }

  /**
   * Sanitize HTML using DOMPurify if available, otherwise return as-is
   * @param {string} html - HTML to sanitize
   * @returns {string} Sanitized HTML
   */
  function sanitizeHtml(html) {
    if (typeof DOMPurify !== "undefined") {
      return DOMPurify.sanitize(html, {
        ALLOWED_TAGS: ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'br', 'strong', 'em', 'u', 'a', 'ul', 'ol', 'li', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'code', 'pre', 'blockquote', 'hr', 'input', 'img'],
        ALLOWED_ATTR: ['href', 'src', 'alt', 'title', 'type', 'checked', 'disabled'],
        ADD_ATTR: ['target'],
        FORBID_TAGS: ['style', 'form', 'input', 'button', 'textarea', 'select', 'iframe', 'script', 'meta', 'link', 'object', 'embed', 'param', 'applet', 'frame', 'frameset', 'layer', 'ilayer', 'bgsound', 'title', 'base'],
        FORBID_ATTR: ['on*', 'style', 'formaction', 'xlink:href']
      });
    }
    // Fallback: return HTML without sanitization (not recommended for untrusted content)
    console.warn('[markdown_renderer] DOMPurify not available, skipping HTML sanitization');
    return html;
  }
  
  /**
   * Render Markdown and insert into DOM element with syntax highlighting
   * @param {string} markdown - The markdown text to render
   * @param {string|HTMLElement} element - CSS selector or DOM element
   * @param {Object} options - Rendering options
   * @returns {Promise<void>}
   */
  async function renderMarkdownToElement(markdown, element, options = {}) {
    try {
      const html = await renderMarkdown(markdown);
      const sanitizedHtml = sanitizeHtml(html);
      const target =
        typeof element === "string"
        ? document.querySelector(element)
        : element;
  
      if (target) {
        target.innerHTML = sanitizedHtml;
  
        // Apply syntax highlighting to code blocks
        if (options.applyHighlight !== false && typeof hljs !== "undefined") {
          target.querySelectorAll("pre code").forEach((block) => {
            hljs.highlightElement(block);
          });
        }
      } else {
        console.warn("Target element not found:", element);
      }
    } catch (error) {
      console.error('[markdown_renderer] Error rendering markdown:', error);
      const target =
        typeof element === "string"
        ? document.querySelector(element)
        : element;
      if (target) {
        target.innerHTML = '<div class="error" style="background: rgba(248, 113, 113, 0.1); border: 1px solid var(--red); padding: 1em; border-radius: 6px; color: var(--red);">Error rendering content. Please try again.</div>';
      }
    }
  }

  /**
   * Display CrewAI result with enhanced formatting
   * @param {string} rawOutput - Raw output from crew
   * @param {string|HTMLElement} element - Target element
   * @param {Object} options - Rendering options
   * @returns {Promise<void>}
   */
  async function displayCrewAIResult(rawOutput, element, options = {}) {
    await renderMarkdownToElement(rawOutput, element, options);
  }

  /**
   * Display loading state during rendering
   * @param {string} elementId - ID of the element to update
   * @param {string} step - Current step (fetching, analyzing, rendering, complete)
   */
  function showRenderingState(elementId, step) {
    const states = {
      fetching: "📊 Fetching rates...",
      analyzing: "🤖 Analyzing with CrewAI...",
      rendering: "📝 Formatting results...",
      complete: "✅ Analysis complete!"
    };
    const element = document.getElementById(elementId);
    if (element) {
      element.textContent = states[step] || step;
    }
  }

  // Export to global scope
  global.renderMarkdown = renderMarkdown;
  global.renderMarkdownSafe = renderMarkdownSafe;
  global.renderMarkdownToElement = renderMarkdownToElement;
  global.displayCrewAIResult = displayCrewAIResult;
  global.escapeHtml = escapeHtml;
  global.ensureMarkedLoaded = ensureMarkedLoaded;
  global.showRenderingState = showRenderingState;
  global.loadHighlightJS = loadHighlightJS;
})(window);
