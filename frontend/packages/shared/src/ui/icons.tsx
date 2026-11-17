/** Icon aliases keep feature code independent of the icon package. */
import React, { forwardRef } from "react";
import {
  Plug, LayoutGrid, Mic, Palette, BookOpen, GitBranch, Lightbulb, CircleCheck, Eraser, X, Server, CloudUpload, Code, Columns2, SlidersHorizontal, Copy, Gauge, Trash2, Download, Expand, FlaskConical, EyeOff, Eye, FolderOpen, Type, HardDrive, History, Info, KeyRound, Link, LoaderCircle, LockKeyhole, MessageSquare, Paperclip, CirclePause, Image, CirclePlay, Plus, CircleHelp, RotateCw, Bot, Rocket, Save, Scissors, Search, Send, Settings, Volume2, Square, ArrowLeftRight, Zap, LockKeyholeOpen, User, Video, type LucideIcon, type LucideProps,
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
