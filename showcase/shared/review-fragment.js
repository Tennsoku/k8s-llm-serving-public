"use strict";

const MAX_REVIEW_BYTES = 256 * 1024;
const ANALYSIS_STATUSES = new Set(["draft", "reviewed", "final"]);

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function fragmentId(url) {
  assert(url.hash.length > 1, "review URL 必须包含 fragment id。");
  try {
    return decodeURIComponent(url.hash.slice(1));
  } catch (error) {
    throw new Error("review fragment id 无法解码：" + error.message);
  }
}

function rebaseLinks(element, sourceUrl) {
  for (const anchor of element.querySelectorAll("a[href]")) {
    const href = anchor.getAttribute("href");
    if (!href || href.startsWith("#")) continue;
    anchor.href = new URL(href, sourceUrl).href;
  }
}

export async function loadReviewFragment(inputUrl, {signal} = {}) {
  const requestedUrl = new URL(inputUrl);
  assert(["http:", "https:"].includes(requestedUrl.protocol), "review URL 只允许 http/https。");
  assert(requestedUrl.origin === window.location.origin, "review URL 必须与 showcase 同源。");
  assert(requestedUrl.pathname.endsWith(".md"), "analysis_path 必须指向 Markdown review。");
  const id = fragmentId(requestedUrl);
  const sourceUrl = new URL(requestedUrl);
  sourceUrl.hash = "";

  const response = await fetch(sourceUrl, {cache: "no-store", signal});
  if (!response.ok) throw new Error("读取 " + sourceUrl.pathname + " 返回 HTTP " + response.status + "。");
  const finalUrl = new URL(response.url || sourceUrl);
  assert(finalUrl.origin === requestedUrl.origin, "review redirect 必须保持同源。");
  const contentLength = Number(response.headers.get("content-length"));
  if (Number.isFinite(contentLength) && contentLength > MAX_REVIEW_BYTES) {
    throw new Error("review 超过 256 KiB 展示层限制。");
  }
  const text = await response.text();
  if (new TextEncoder().encode(text).byteLength > MAX_REVIEW_BYTES) {
    throw new Error("review 超过 256 KiB 展示层限制。");
  }

  const parsed = new DOMParser().parseFromString(text, "text/html");
  const sourceElement = parsed.getElementById(id);
  assert(sourceElement, "review 缺少 #" + id + " block。");
  assert(sourceElement.classList.contains("review-fragment"), "#" + id + " 必须声明 review-fragment class。");
  const status = sourceElement.dataset.analysisStatus;
  assert(ANALYSIS_STATUSES.has(status), "#" + id + " 的 data-analysis-status 无效。");
  rebaseLinks(sourceElement, finalUrl);

  const element = document.importNode(sourceElement, true);
  const canonicalUrl = new URL(finalUrl);
  canonicalUrl.hash = "#" + encodeURIComponent(id);
  return {element, status, sourceUrl: canonicalUrl};
}

export function renderReviewFragment(host, review) {
  host.replaceChildren(review.element);
  host.setAttribute("aria-busy", "false");
}

export function renderReviewError(host, message) {
  const notice = document.createElement("p");
  notice.className = "review-fragment-error";
  notice.textContent = message;
  host.replaceChildren(notice);
  host.setAttribute("aria-busy", "false");
}
