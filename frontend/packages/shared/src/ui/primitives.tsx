/**
 * Unified UI component adapter layer.
 * Currently backed by Ant Design v5 (`antd`) with a clean Light Studio Theme,
 * isolated here so all feature apps can migrate smoothly to a custom UI library later.
 */
import React from "react";
import {
  Alert,
  App as AntdApp,
  Badge,
  Button,
  Card,
  Collapse,
  ConfigProvider,
  Divider,
  Drawer,
  Empty,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Popover,
  Progress,
  Radio,
  Segmented,
  Select,
  Slider,
  Space,
  Switch,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  theme,
} from "antd";

export interface StudioThemeProviderProps {
  children: React.ReactNode;
}

export function StudioThemeProvider({ children }: StudioThemeProviderProps) {
  return (
    <ConfigProvider
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: {
          colorPrimary: "#2563eb",
          colorInfo: "#2563eb",
          colorSuccess: "#059669",
          colorWarning: "#d97706",
          colorError: "#dc2626",
          colorBgBase: "#ffffff",
          colorBgLayout: "#f4f6fa",
          colorBgContainer: "#ffffff",
          colorBgElevated: "#ffffff",
          colorText: "#0f172a",
          colorTextSecondary: "#475569",
          colorTextTertiary: "#64748b",
          colorBorder: "#94a3b8",
          colorBorderSecondary: "#e2e8f0",
          borderRadius: 10,
          fontSize: 14,
        },
        components: {
          Card: {
            headerBg: "#ffffff",
            colorBorderSecondary: "#e2e8f0",
            paddingLG: 18,
          },
          Button: {
            controlHeight: 36,
            controlHeightLG: 44,
            fontWeight: 500,
          },
          Input: {
            controlHeight: 36,
            colorBorder: "#8494ab",
          },
          InputNumber: {
            controlHeight: 36,
            colorBorder: "#8494ab",
          },
          Select: {
            controlHeight: 36,
            colorBorder: "#8494ab",
          },
          Segmented: {
            trackBg: "#eef2f7",
            itemSelectedBg: "#ffffff",
            itemSelectedColor: "#0f172a",
            itemColor: "#475569",
          },
          Tabs: {
            itemSelectedColor: "#2563eb",
            inkBarColor: "#2563eb",
            titleFontSize: 14,
          },
          Slider: {
            railBg: "#dbe3ee",
            railHoverBg: "#cbd5e1",
            trackBg: "#2563eb",
            trackHoverBg: "#1d4ed8",
            handleColor: "#2563eb",
          },
        },
      }}
    >
      <AntdApp>{children}</AntdApp>
    </ConfigProvider>
  );
}

export function useStudioFeedback() {
  const { message, modal, notification } = AntdApp.useApp();
  return { message, modal, notification };
}

export const TextArea = Input.TextArea;
export const RadioGroup = Radio.Group;
export const RadioButton = Radio.Button;
export const Title = Typography.Title;
export const Text = Typography.Text;
export const Paragraph = Typography.Paragraph;

export {
  Alert,
  Badge,
  Button,
  Card,
  Collapse,
  Divider,
  Drawer,
  Empty,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Popover,
  Progress,
  Radio,
  Segmented,
  Select,
  Slider,
  Space,
  Switch,
  Tabs,
  Tag,
  Tooltip,
  Typography,
};

export {
  ApiOutlined,
  AppstoreOutlined,
  AudioOutlined,
  BgColorsOutlined,
  BookOutlined,
  BranchesOutlined,
  BulbOutlined,
  CheckCircleFilled,
  ClearOutlined,
  CloseOutlined,
  CloudServerOutlined,
  CloudUploadOutlined,
  CodeOutlined,
  ColumnWidthOutlined,
  ControlOutlined,
  CopyOutlined,
  DashboardOutlined,
  DeleteOutlined,
  DownloadOutlined,
  ExpandOutlined,
  ExperimentOutlined,
  EyeInvisibleOutlined,
  EyeOutlined,
  FolderOpenOutlined,
  FontColorsOutlined,
  HddOutlined,
  HistoryOutlined,
  InfoCircleOutlined,
  KeyOutlined,
  LinkOutlined,
  LoadingOutlined,
  LockOutlined,
  MessageOutlined,
  PaperClipOutlined,
  PauseCircleOutlined,
  PictureOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  QuestionCircleOutlined,
  ReloadOutlined,
  RobotOutlined,
  RocketOutlined,
  SaveOutlined,
  ScissorOutlined,
  SearchOutlined,
  SendOutlined,
  SettingOutlined,
  SlidersOutlined,
  SoundOutlined,
  StopOutlined,
  SwapOutlined,
  ThunderboltOutlined,
  UnlockOutlined,
  UserOutlined,
  VideoCameraOutlined,
} from "@ant-design/icons";
