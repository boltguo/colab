/** Icon aliases keep feature code independent of the icon package. */
import React, { forwardRef } from "react";
import {
  Plug, LayoutGrid, Mic, Palette, BookOpen, GitBranch, Lightbulb, CircleCheck, Eraser, X, Server, CloudUpload, Code, Columns2, SlidersHorizontal, Copy, Gauge, Trash2, Download, Expand, FlaskConical, EyeOff, Eye, FolderOpen, Type, Globe, HardDrive, History, Info, KeyRound, Link, LoaderCircle, LockKeyhole, MessageSquare, Paperclip, CirclePause, Image, CirclePlay, Plus, CircleHelp, RotateCw, Bot, Rocket, Save, Scissors, Search, Send, Settings, Volume2, Square, ArrowLeftRight, Zap, LockKeyholeOpen, User, Video, type LucideIcon, type LucideProps,
} from "lucide-react";

function studioIcon(Icon: LucideIcon, animate = false) {
  return forwardRef<SVGSVGElement, LucideProps & { spin?: boolean }>(function StudioIcon({ spin = animate, className, ...props }, ref) {
    return <Icon size="1em" strokeWidth={1.8} aria-hidden="true" {...props} ref={ref}
      className={`studio-icon ${spin ? "studio-icon-spin" : ""} ${className || ""}`} />;
  });
}

export const ApiOutlined = studioIcon(Plug);
export const AppstoreOutlined = studioIcon(LayoutGrid);
export const AudioOutlined = studioIcon(Mic);
export const BgColorsOutlined = studioIcon(Palette);
export const BookOutlined = studioIcon(BookOpen);
export const BranchesOutlined = studioIcon(GitBranch);
export const BulbOutlined = studioIcon(Lightbulb);
export const CheckCircleFilled = studioIcon(CircleCheck);
export const ClearOutlined = studioIcon(Eraser);
export const CloseOutlined = studioIcon(X);
export const CloudServerOutlined = studioIcon(Server);
export const CloudUploadOutlined = studioIcon(CloudUpload);
export const CodeOutlined = studioIcon(Code);
export const ColumnWidthOutlined = studioIcon(Columns2);
export const ControlOutlined = studioIcon(SlidersHorizontal);
export const CopyOutlined = studioIcon(Copy);
export const DashboardOutlined = studioIcon(Gauge);
export const DeleteOutlined = studioIcon(Trash2);
export const DownloadOutlined = studioIcon(Download);
export const ExpandOutlined = studioIcon(Expand);
export const ExperimentOutlined = studioIcon(FlaskConical);
export const EyeInvisibleOutlined = studioIcon(EyeOff);
export const EyeOutlined = studioIcon(Eye);
export const FolderOpenOutlined = studioIcon(FolderOpen);
export const FontColorsOutlined = studioIcon(Type);
export const GlobalOutlined = studioIcon(Globe);
export const GithubOutlined = forwardRef<SVGSVGElement, LucideProps>(function GithubOutlined(
  { size = "1em", className, ...props },
  ref,
) {
  return (
    <svg
      ref={ref}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
      {...props}
      className={`studio-icon ${className || ""}`}
    >
      <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12" />
    </svg>
  );
});
export const HddOutlined = studioIcon(HardDrive);
export const HistoryOutlined = studioIcon(History);
export const InfoCircleOutlined = studioIcon(Info);
export const KeyOutlined = studioIcon(KeyRound);
export const LinkOutlined = studioIcon(Link);
export const LoadingOutlined = studioIcon(LoaderCircle, true);
export const LockOutlined = studioIcon(LockKeyhole);
export const MessageOutlined = studioIcon(MessageSquare);
export const PaperClipOutlined = studioIcon(Paperclip);
export const PauseCircleOutlined = studioIcon(CirclePause);
export const PictureOutlined = studioIcon(Image);
export const PlayCircleOutlined = studioIcon(CirclePlay);
export const PlusOutlined = studioIcon(Plus);
export const QuestionCircleOutlined = studioIcon(CircleHelp);
export const ReloadOutlined = studioIcon(RotateCw);
export const RobotOutlined = studioIcon(Bot);
export const RocketOutlined = studioIcon(Rocket);
export const SaveOutlined = studioIcon(Save);
export const ScissorOutlined = studioIcon(Scissors);
export const SearchOutlined = studioIcon(Search);
export const SendOutlined = studioIcon(Send);
export const SettingOutlined = studioIcon(Settings);
export const SlidersOutlined = studioIcon(SlidersHorizontal);
export const SoundOutlined = studioIcon(Volume2);
export const StopOutlined = studioIcon(Square);
export const SwapOutlined = studioIcon(ArrowLeftRight);
export const ThunderboltOutlined = studioIcon(Zap);
export const UnlockOutlined = studioIcon(LockKeyholeOpen);
export const UserOutlined = studioIcon(User);
export const VideoCameraOutlined = studioIcon(Video);
