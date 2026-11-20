import React from "react";
import { useStudioLocale } from "../i18n";
import { Button, CloseOutlined, RocketOutlined } from "../ui/primitives";

interface GenerateButtonProps {
  busy?: boolean;
  queued?: boolean;
  disabled?: boolean;
  label?: string;
  onGenerate: () => void;
  onCancel?: () => void;
}

/** Standard full-width m3eui generation action placed at the bottom of the workbench. */
export function GenerateButton({
  busy,
  queued,
  disabled,
  label,
  onGenerate,
  onCancel,
}: GenerateButtonProps) {
  const { t } = useStudioLocale();
  const canCancel = Boolean(queued && onCancel);

  return (
    <div className="studio-generate-action">
      {canCancel ? (
        <Button
          htmlType="button"
          size="large"
          block
          danger
          icon={<CloseOutlined />}
          onClick={onCancel}
        >
          {t("Cancel queue", "取消排队")}
        </Button>
      ) : (
        <Button
          htmlType="button"
          type="primary"
          size="large"
          block
          icon={<RocketOutlined />}
          loading={Boolean(busy)}
          disabled={disabled}
          onClick={onGenerate}
        >
          {busy ? t("Generating…", "生成中……") : (label ?? t("Generate", "开始生成"))}
        </Button>
      )}
    </div>
  );
}
