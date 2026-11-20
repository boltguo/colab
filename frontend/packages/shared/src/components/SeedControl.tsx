import React, { useId } from "react";
import { useStudioLocale } from "../i18n";
import { IconButton, Input, ReloadOutlined, Tooltip } from "../ui/primitives";

export function SeedControl({
  value,
  max = Number.MAX_SAFE_INTEGER,
  onChange,
  onLockedChange,
}: {
  value: number;
  max?: number;
  onChange: (value: number) => void;
  onLockedChange?: (locked: boolean) => void;
}) {
  const { t } = useStudioLocale();
  const id = useId();
  return (
    <div className="studio-field-group studio-seed-setting">
      <div className="studio-field-label">
        <label htmlFor={id}>{t("Seed", "种子")}</label>
        <span className="studio-field-hint">{t("0 = random", "0 为随机")}</span>
      </div>
      <div className="studio-seed-setting__controls">
        <Input
          id={id}
          aria-label={t("Seed", "种子")}
          className="studio-seed-input studio-tabular"
          inputMode="numeric"
          pattern="[0-9]*"
          maxLength={String(max).length}
          style={{ inlineSize: "100%" }}
          value={String(value)}
          onValueChange={(raw) => {
            if (!/^\d*$/.test(raw)) return;
            const seed = Number(raw || 0);
            if (!Number.isSafeInteger(seed) || seed > max) return;
            onChange(seed);
            onLockedChange?.(seed > 0);
          }}
        />
        <Tooltip title={t("Randomize seed", "使用随机种子")}>
          <IconButton
            className="studio-seed-reset-btn"
            variant="standard"
            size="xs"
            type="button"
            icon={<ReloadOutlined />}
            aria-label={t("Randomize seed", "使用随机种子")}
            onClick={() => {
              onChange(0);
              onLockedChange?.(false);
            }}
          />
        </Tooltip>
      </div>
    </div>
  );
}
