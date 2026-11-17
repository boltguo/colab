/** Shared Studio adapter. Keep component-library details out of feature apps. */
import React, { forwardRef, useMemo, useState } from "react";
import {
  Alert as M3Alert, AlertDialog, Badge as M3Badge, Button as M3Button,
  ButtonGroup, Card as M3Card, Chip, Dialog, Divider as M3Divider, Empty as M3Empty,
  IconButton, LinearProgressIndicator, M3EProvider, NumberField, Popover as M3Popover,
  ScrollArea, Select as M3Select, Slider as M3Slider, Switch as M3Switch, Tab, Tabs as M3Tabs,
  TabsList, TabsPanel, TextField, Tooltip as M3Tooltip, useM3EToast,
  type M3EButtonActionProps, type M3ECardProps, type M3EChipLabelProps, type M3ENumberFieldProps,
  type M3ESelectSingleProps, type M3ESliderProps, type M3ESwitchProps,
  type M3ETextFieldSingleLineProps,
} from "m3eui";

export function StudioThemeProvider({ children }: { children: React.ReactNode }) {
  return <M3EProvider initialColorMode="light" initialLocale="zh-CN">{children}</M3EProvider>;
}

export { Dialog, IconButton, ScrollArea };

export function useStudioFeedback() {
  const { toast } = useM3EToast();
  const message = useMemo(() => ({
    success: (title: React.ReactNode) => toast({ title, type: "success", timeout: 3500 }),
    error: (title: React.ReactNode) => toast({ title, type: "error", timeout: 6000 }),
    warning: (title: React.ReactNode) => toast({ title, type: "warning", timeout: 4500 }),
    info: (title: React.ReactNode) => toast({ title, type: "info", timeout: 3500 }),
  }), [toast]);
  return { message };
}

type Size = "small" | "middle" | "large";
type ButtonProps = Omit<M3EButtonActionProps, "type" | "size" | "children"> & {
  children?: React.ReactNode;
  type?: "primary" | "default" | "dashed" | "link" | "text";
  htmlType?: "button" | "submit" | "reset";
  size?: Size;
  icon?: React.ReactNode;
  block?: boolean;
  danger?: boolean;
  ghost?: boolean;
  download?: string;
};
export const Button = forwardRef<HTMLElement, ButtonProps>(function Button({
  type = "default", htmlType = "button", size, icon, block, danger, ghost,
  children, ...props
}, ref) {
  const variant = type === "link" || type === "text" ? "text"
    : type === "primary" && !ghost ? "filled" : "outlined";
  if (icon && children == null && !props.href) {
    return <IconButton {...props} ref={ref} icon={icon} type={htmlType}
      aria-label={props["aria-label"] || props.title || "操作"}
      variant={variant === "text" ? "standard" : variant}
      intent={danger ? "danger" : "default"} size={size === "small" ? "xs" : "sm"} />;
  }
  return <M3Button {...props} ref={ref} type={htmlType} variant={variant}
    intent={danger ? "danger" : "default"} size={size === "small" ? "xs" : size === "large" ? "md" : "sm"}
    leadingIcon={icon} fullWidth={block}>{children}</M3Button>;
});

export function Card({ title, extra, children, size: _size, style, ...props }:
  M3ECardProps & { extra?: React.ReactNode; size?: Size }) {
  // Match the Overview's quiet scene surfaces without altering the theme palette.
  return <M3Card {...props} style={{ backgroundColor: "var(--m3e-color-surface-container-low)",
    borderRadius: "var(--m3e-shape-corner-extra-large)", ...style }} title={(title || extra) && <div className="studio-card-heading">
      <div className="studio-card-title">{title}</div>
      {extra && <div className="studio-card-extra">{extra}</div>}
    </div>}>
    {children}
  </M3Card>;
}

export function ChoiceButton({ active, children, ...props }:
  Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "value"> & { active: boolean }) {
  return <M3Button {...props} pressed={active} variant="tonal" shape="square"
    style={{ height: "auto", minHeight: 88, paddingBlock: 12, inlineSize: "100%", ...props.style }}>
    <span style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>{children}</span>
  </M3Button>;
}

type InputProps = Omit<M3ETextFieldSingleLineProps, "label"> & {
  label?: React.ReactNode;
  "aria-label"?: string;
  size?: Size;
  allowClear?: boolean;
  prefix?: React.ReactNode;
  autoCorrect?: string;
  autoCapitalize?: string;
  spellCheck?: boolean;
  onKeyDown?: React.KeyboardEventHandler<HTMLDivElement>;
  onPressEnter?: () => void;
};
const StudioInput = forwardRef<HTMLInputElement, InputProps>(function StudioInput({
  label, size: _size, allowClear, prefix, autoCorrect, autoCapitalize, spellCheck,
  onKeyDown, onPressEnter, style, className, "aria-label": ariaLabel, ...props
}, ref) {
  return <div className={`studio-input ${className || ""}`} style={style}
    autoCorrect={autoCorrect} autoCapitalize={autoCapitalize} spellCheck={spellCheck}
    onKeyDown={(event) => {
      onKeyDown?.(event);
      if (event.key === "Enter" && !event.defaultPrevented && !event.nativeEvent.isComposing && event.keyCode !== 229) {
        onPressEnter?.();
      }
    }}>
    <TextField {...props} ref={ref} label={label ?? (ariaLabel ? <span className="studio-visually-hidden">{ariaLabel}</span> : undefined)} labelPosition="outside"
      clearable={allowClear} leadingIcon={prefix} />
  </div>;
});
const Password = forwardRef<HTMLInputElement, InputProps>(function Password(props, ref) {
  return <StudioInput {...props} ref={ref} type="password" />;
});
export const Input = Object.assign(StudioInput, { Password });

type TextAreaProps = Pick<React.TextareaHTMLAttributes<HTMLTextAreaElement>,
  "id" | "name" | "rows" | "maxLength" | "placeholder" | "disabled" | "className" | "style" | "aria-label"> & {
  value?: string;
  onValueChange?: (value: string) => void;
  showCount?: boolean;
  onKeyDown?: React.KeyboardEventHandler<HTMLDivElement>;
};
export const TextArea = forwardRef<HTMLTextAreaElement, TextAreaProps>(function TextArea({
  showCount, onKeyDown, className, style, "aria-label": ariaLabel, ...props
}, ref) {
  return <div className={`studio-input studio-textarea ${className || ""}`} style={style} onKeyDown={onKeyDown}>
    <TextField {...props} ref={ref} label={ariaLabel ? <span className="studio-visually-hidden">{ariaLabel}</span> : undefined} multiline labelPosition="outside" showCharacterCount={showCount} />
  </div>;
});

export function InputNumber({ size: _size, addonBefore, addonAfter, precision, controls = true,
  placeholder, onBlur, onChange, style, className, ...props }:
  M3ENumberFieldProps & {
    size?: Size;
    addonBefore?: React.ReactNode;
    addonAfter?: React.ReactNode;
    precision?: number;
    controls?: boolean;
    placeholder?: string;
    onBlur?: React.FocusEventHandler<HTMLDivElement>;
    onChange?: (value: number | null) => void;
  }) {
  return <div className={`studio-number studio-tabular ${controls ? "" : "studio-number-plain"} ${className || ""}`} style={style} onBlur={onBlur}>
    {addonBefore && <span className="studio-number-affix">{addonBefore}</span>}
    <NumberField {...props} ref={(input) => { if (input) input.placeholder = placeholder || ""; }}
      format={{ useGrouping: false, maximumFractionDigits: precision ?? 10 }} onValueChange={onChange} />
    {addonAfter && <span className="studio-number-affix">{addonAfter}</span>}
  </div>;
}

export function Select<Value extends string>({ size: _size, onChange, ...props }:
  Omit<M3ESelectSingleProps<Value>, "onValueChange"> & { size?: Size; onChange?: (value: Value) => void }) {
  return <M3Select {...props} labelPosition="outside" className={`studio-select ${props.className || ""}`}
    onValueChange={(value) => { if (value !== null) onChange?.(value); }} />;
}

type SegmentValue = string | number;
type SegmentOption<Value> = Value | { value: Value; label: React.ReactNode; icon?: React.ReactNode; disabled?: boolean };
export function Segmented<Value extends SegmentValue>({ options, value, onChange, disabled, block, size, className, style, variant = "tonal", "aria-label": ariaLabel }:
  { options: SegmentOption<Value>[]; value: Value; onChange?: (value: Value) => void;
    disabled?: boolean; block?: boolean; size?: Size; className?: string; style?: React.CSSProperties;
    variant?: "tonal" | "outlined"; "aria-label"?: string }) {
  return <div className={`studio-segmented ${className || ""}`} data-block={block || undefined} style={style}>
    <ButtonGroup variant="connected" selectionMode="single" size={size === "small" ? "xs" : "sm"}
      buttonVariant={variant} value={[String(value)]} aria-label={ariaLabel}
      items={options.map((option) => {
        const item = typeof option === "object" ? option : { value: option, label: option };
        return { ...item, value: String(item.value), disabled: disabled || item.disabled };
      })}
      onValueChange={(next) => {
        // Keep a selection and preserve numeric values (e.g. batch size).
        const option = options.find((item) => String(typeof item === "object" ? item.value : item) === next[0]);
        if (option !== undefined) onChange?.(typeof option === "object" ? option.value : option);
      }} />
  </div>;
}

export function Slider({ onChange, tooltip, marks, ...props }: Omit<M3ESliderProps<number>, "onValueChange"> & {
  onChange?: (value: number) => void;
  tooltip?: { formatter?: (value?: number) => React.ReactNode };
  marks?: Record<number, React.ReactNode>;
}) {
  return <div className="studio-slider" style={props.style}>
    <M3Slider {...props} style={undefined} size="sm" onValueChange={onChange}
      formatValue={tooltip?.formatter ? (value) => String(tooltip.formatter?.(value)) : props.formatValue} />
    {marks && <div className="studio-slider-marks">{Object.entries(marks).map(([value, label]) =>
      <span key={value}>{label}</span>)}</div>}
  </div>;
}
export function Switch({ size: _size, onChange, ...props }: M3ESwitchProps & {
  size?: Size; onChange?: (checked: boolean) => void;
}) {
  return <M3Switch {...props} onCheckedChange={onChange} />;
}

export function Alert({ type = "info", message, description, showIcon, ...props }:
  Omit<React.ComponentProps<typeof M3Alert>, "title"> & {
    type?: "info" | "success" | "warning" | "error";
    message?: React.ReactNode; description?: React.ReactNode; showIcon?: boolean;
  }) {
  return <M3Alert {...props} severity={type} title={message} icon={showIcon ? props.icon : false}>{description}</M3Alert>;
}
export function Tag({ color, children, ...props }: Omit<M3EChipLabelProps, "tone"> & { color?: string }) {
  const tone = color === "error" || color === "red" ? "error" : color === "warning" || color === "orange" ? "warning"
    : color === "success" || color === "green" ? "success"
    : color === "blue" || color === "processing" || color === "geekblue" ? "primary" : "neutral";
  return <Chip {...props} tone={tone} size="sm">{children}</Chip>;
}
export function Badge({ status, text, color: _color, ...props }:
  Omit<React.ComponentProps<typeof M3Badge>, "color"> & { status?: string; text?: React.ReactNode; color?: string }) {
  return status ? <Tag color={status}>{text}</Tag> : <M3Badge {...props} color="primary" />;
}
export function Tooltip({ title, children }: { title?: React.ReactNode; children: React.ReactElement }) {
  const button = children as React.ReactElement<ButtonProps>;
  const trigger = children.type === Button && typeof title === "string" && button.props.icon
    && button.props.children == null && !button.props["aria-label"]
    ? React.cloneElement(button, { "aria-label": title }) : children;
  return <M3Tooltip content={title} disabled={!title}>{trigger}</M3Tooltip>;
}
export function Popover({ content, children, trigger, placement, ...props }:
  Omit<React.ComponentProps<typeof M3Popover>, "trigger" | "children"> & {
    content: React.ReactNode; children: React.ReactElement; trigger?: string | string[]; placement?: string;
  }) {
  return <M3Popover {...props} trigger={children} openOnHover={Array.isArray(trigger) && trigger.includes("hover")}
    side="bottom" align={placement?.endsWith("Right") ? "end" : "center"}
    style={{ maxWidth: "min(480px, calc(100vw - 24px))", ...props.style }}>{content}</M3Popover>;
}
export function Popconfirm({ children, title, onConfirm, okText = "确定", cancelText = "取消", disabled }:
  { children: React.ReactElement; title: React.ReactNode; onConfirm: () => void; okText?: string; cancelText?: string; disabled?: boolean }) {
  const [open, setOpen] = useState(false);
  if (disabled) return children;
  return <AlertDialog title={title} trigger={children} open={open} onOpenChange={setOpen}
    actions={<>
      <Button onClick={() => setOpen(false)}>{cancelText}</Button>
      <Button type="primary" danger onClick={() => { onConfirm(); setOpen(false); }}>{okText}</Button>
    </>} />;
}
export function Modal({ title, children, open, onCancel, onOk, okText = "确定", cancelText = "取消", confirmLoading = false }:
  { title: React.ReactNode; children: React.ReactNode; open: boolean; onCancel: () => void; onOk: () => void; okText?: string; cancelText?: string; confirmLoading?: boolean }) {
  return <Dialog title={title} open={open} onOpenChange={(next) => { if (!next) onCancel(); }}
    actions={<><Button onClick={onCancel}>{cancelText}</Button><Button type="primary" disabled={confirmLoading} onClick={onOk}>{confirmLoading ? "保存中…" : okText}</Button></>}>
    {children}
  </Dialog>;
}
export function Tabs({ items, className }: { items: Array<{ key: string; label: React.ReactNode; children: React.ReactNode }>; className?: string }) {
  return <M3Tabs className={className} defaultValue={items[0]?.key} variant="secondary" scrollable>
    <TabsList aria-label="API 调用示例">{items.map((item) => <Tab key={item.key} value={item.key}>{item.label}</Tab>)}</TabsList>
    {items.map((item) => <TabsPanel key={item.key} value={item.key}>{item.children}</TabsPanel>)}
  </M3Tabs>;
}
export function Progress({ percent, showInfo, style }: { percent: number; status?: string; showInfo?: boolean; size?: Size; style?: React.CSSProperties }) {
  return <LinearProgressIndicator value={percent} showValue={showInfo} aria-label="任务进度" style={style} />;
}
function EmptyState({ image: _image, ...props }: React.ComponentProps<typeof M3Empty> & { image?: unknown }) {
  return <M3Empty {...props} compact />;
}
export const Empty = Object.assign(EmptyState, { PRESENTED_IMAGE_SIMPLE: undefined });

type SpaceProps = React.HTMLAttributes<HTMLDivElement> & { size?: number | [number, number]; direction?: "horizontal" | "vertical"; wrap?: boolean; block?: boolean };
function Stack({ size = 8, direction, wrap, block: _block, style, ...props }: SpaceProps) {
  const gap = Array.isArray(size) ? `${size[1]}px ${size[0]}px` : size;
  return <div {...props} style={{ display: "flex", flexDirection: direction === "vertical" ? "column" : "row",
    alignItems: direction === "vertical" ? "stretch" : "center", flexWrap: wrap ? "wrap" : undefined, gap, ...style }} />;
}
export const Space = Object.assign(Stack, { Compact: (props: SpaceProps) => <Stack {...props} size={0} /> });
export function Divider({ type, style }: { type?: "horizontal" | "vertical"; style?: React.CSSProperties }) {
  return type === "vertical" ? <span className="studio-divider-vertical" style={style} /> : <M3Divider style={style} />;
}
export function Text({ strong, code, type, ellipsis, style, children, ...props }:
  React.HTMLAttributes<HTMLSpanElement> & { strong?: boolean; code?: boolean; type?: "secondary"; ellipsis?: { tooltip?: string } }) {
  const Element = code ? "code" : "span";
  return <Element {...props} title={ellipsis?.tooltip} className={`studio-text ${code ? "studio-text-code" : ""} ${props.className || ""}`}
    style={{ fontWeight: strong ? 600 : undefined, color: type === "secondary" ? "var(--studio-text-muted)" : undefined,
      ...(ellipsis ? { overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", display: "block" } : {}), ...style }}>{children}</Element>;
}

export * from "./icons";
