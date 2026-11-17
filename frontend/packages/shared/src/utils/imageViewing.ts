export function fitImageScale(width: number, height: number, availableWidth: number, availableHeight: number): number {
  if (width <= 0 || height <= 0 || availableWidth <= 0 || availableHeight <= 0) return 1;
  return Math.min(1, availableWidth / width, availableHeight / height);
}

export function imageDownloadUrl(url: string): string {
  return `${url}${url.includes("?") ? "&" : "?"}download=1`;
}
