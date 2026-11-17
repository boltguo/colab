import React, { useId } from "react";
import { Button, RocketOutlined, Select } from "../ui/primitives";

interface GenerateDockProps {
  format: string;
  formats: Array<{ label: string; value: string }>;
  onFormatChange: (format: string) => void;
  quantity?: number;
  maxQuantity?: number;
  onQuantityChange?: (quantity: number) => void;
  busy?: boolean;
  queued?: boolean;
  disabled?: boolean;
  label?: string;
  onGenerate: () => void;
  onCancel?: () => void;
}

/** Keep output controls and the primary action consistent across media studios. */
export function GenerateDock({ format, formats, onFormatChange, quantity, maxQuantity = 4,
  onQuantityChange, busy, queued, disabled, label = "开始生成", onGenerate, onCancel }: GenerateDockProps) {
  const formatId = useId();
  const quantityId = useId();
  const canCancel = queued && onCancel;
  return <div className="studio-action-dock studio-generate-dock" data-has-quantity={quantity !== undefined || undefined}>
    <div className="studio-generate-dock__outputs">
      <div className="studio-generate-dock__field">
        <label htmlFor={formatId}>格式</label>
        <Select id={formatId} aria-label="输出格式" value={format} onChange={onFormatChange} options={formats} />
      </div>
      {quantity !== undefined && onQuantityChange && <div className="studio-generate-dock__field">
        <label htmlFor={quantityId}>数量</label>
        <Select id={quantityId} aria-label="生成数量" value={String(quantity)} onChange={(value) => onQuantityChange(Number(value))}
          options={Array.from({ length: maxQuantity }, (_, index) => ({ label: `${index + 1} 张`, value: String(index + 1) }))} />
      </div>}
    </div>
    <Button type="primary" icon={<RocketOutlined />} loading={busy && !canCancel} disabled={disabled}
      onClick={canCancel ? onCancel : onGenerate}>{canCancel ? "取消排队" : busy ? "生成中……" : label}</Button>
  </div>;
}
