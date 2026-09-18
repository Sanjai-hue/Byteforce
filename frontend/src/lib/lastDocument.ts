// The most recently analysed document, remembered per browser so the landing
// page can offer a way back to it. A convenience only: storage can be empty,
// cleared or blocked, and every caller must work without it.
const KEY = "reqguard:last-document";

export function readLastDocument(): string | null {
  try {
    return window.localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function rememberLastDocument(documentId: string): void {
  try {
    window.localStorage.setItem(KEY, documentId);
  } catch {
    /* storage unavailable: nothing to remember */
  }
}
