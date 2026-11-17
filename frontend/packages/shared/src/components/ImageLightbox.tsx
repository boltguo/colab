import React, { useEffect, useState } from "react";
import { Button, Dialog, DownloadOutlined, ScrollArea } from "../ui/primitives";
import { fitImageScale, imageDownloadUrl } from "../utils/imageViewing";
import type { StageImageEntry } from "./ImageCompareStage";

export { imageDownloadUrl } from "../utils/imageViewing";

export function ImageLightbox({ images, open, onClose }: {
  images: StageImageEntry[]; open: boolean; onClose: () => void;
}) {
  const [index, setIndex] = useState(0);
  const [scale, setScale] = useState<number | null>(null);
  const [canvas, setCanvas] = useState<HTMLDivElement | null>(null);
  const [bounds, setBounds] = useState({ width: 1, height: 1 });
  const [natural, setNatural] = useState<{ url: string; width: number; height: number } | null>(null);
  const imageSet = images.map((image) => image.url).join("|");
  const image = images[Math.min(index, images.length - 1)];
  useEffect(() => { setIndex(0); setScale(null); }, [open, imageSet]);
  useEffect(() => { setScale(null); }, [image?.url]);
  useEffect(() => {
    if (!canvas) return;
    const observer = new ResizeObserver(([entry]) => setBounds({ width: entry.contentRect.width, height: entry.contentRect.height }));
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [canvas]);
  if (!image) return null;
  const width = natural?.url === image.url ? natural.width : image.width;
  const height = natural?.url === image.url ? natural.height : image.height;
  const currentScale = scale ?? fitImageScale(width, height, bounds.width, bounds.height);
  const zoom = (factor: number) => setScale(Math.max(0.05, Math.min(4, currentScale * factor)));
  return <Dialog open={open} onOpenChange={(next) => { if (!next) onClose(); }} showCloseButton
    title={`查看图片 · ${width} × ${height}`} className="studio-image-dialog"
    style={{ width: "min(1200px, calc(100vw - 32px))", maxWidth: "none" }}>
    <div className="studio-image-toolbar">
      {images.length > 1 && <><Button size="small" disabled={index === 0} onClick={() => setIndex((value) => value - 1)}>上一张</Button>
        <span className="studio-tabular">{index + 1} / {images.length}</span>
        <Button size="small" disabled={index === images.length - 1} onClick={() => setIndex((value) => value + 1)}>下一张</Button></>}
      <Button size="small" aria-label="缩小图片" onClick={() => zoom(1 / 1.25)}>−</Button>
      <span className="studio-tabular">{Math.round(currentScale * 100)}%</span>
      <Button size="small" aria-label="放大图片" onClick={() => zoom(1.25)}>＋</Button>
      <Button size="small" onClick={() => setScale(null)}>适应窗口</Button>
      <Button size="small" onClick={() => setScale(1)}>原始大小</Button>
      <Button size="small" type="primary" href={imageDownloadUrl(image.url)} download={image.filename} icon={<DownloadOutlined />}>下载原图</Button>
    </div>
    <div ref={setCanvas} className="studio-image-canvas">
      <ScrollArea orientation="both" maxHeight="100%" style={{ height: "100%", width: "100%" }}>
        <div className="studio-image-plane" style={{ width: Math.max(bounds.width, width * currentScale), height: Math.max(bounds.height, height * currentScale) }}>
          <img src={image.url} alt={image.filename} onLoad={(event) => setNatural({ url: image.url, width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })}
            style={{ width: width * currentScale, height: height * currentScale }} />
        </div>
      </ScrollArea>
    </div>
  </Dialog>;
}
