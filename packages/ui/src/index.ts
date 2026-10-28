// Public API of @aip/ui. Every export must be covered by the matching *.test.ts(x) (see exports.test.ts).
export { cn } from "./lib/cn";
export {
  colors,
  fontSize,
  spacing,
  radii,
  density,
  fonts,
  statusTones,
  rootTokens,
  cssVar,
  type StatusTone,
} from "./tokens/tokens";
export { contrastRatio, relativeLuminance, isAccessibleAccent, MIN_TEXT_CONTRAST } from "./tokens/contrast";

export { Badge, badgeVariants, type BadgeProps } from "./components/badge";
export {
  AipMark,
  BadgeLockup,
  EndorsedLockup,
  type AipMarkProps,
  type AipMarkShape,
  type BadgeLockupProps,
  type EndorsedLockupProps,
} from "./components/brand";
export { Button, buttonVariants, type ButtonProps } from "./components/button";
export { Checkbox, type CheckboxProps } from "./components/checkbox";
export { Combobox, type ComboboxOption, type ComboboxProps } from "./components/combobox";
export {
  Dialog,
  DialogTrigger,
  DialogContent,
  DialogTitle,
  DialogDescription,
  DialogClose,
  type DialogContentProps,
} from "./components/dialog";
export {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from "./components/dropdown-menu";
export { FormField, type FormFieldProps, type FormFieldControlProps } from "./components/form-field";
export { Icon, iconNames, type IconName, type IconProps } from "./components/icon";
export { Input, type InputProps } from "./components/input";
export { Label, type LabelProps } from "./components/label";
export { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "./components/select";
export { Spinner, type SpinnerProps } from "./components/spinner";
export { StatusChip, type StatusChipProps } from "./components/status-chip";
export {
  Table,
  TableCaption,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "./components/table";
export { TooltipProvider, Tooltip, TooltipTrigger, TooltipContent } from "./components/tooltip";

// DESIGN-03: the register table standard.
export { RegisterTable, type RegisterTableProps } from "./register/RegisterTable";
export { FilterBar, SEARCH_DEBOUNCE_MS, type FilterBarProps } from "./register/FilterBar";
export {
  ColumnChooser,
  defaultColumns,
  localStorageColumnPrefs,
  type ColumnChooserProps,
  type ColumnPrefsStore,
} from "./register/ColumnChooser";
export { decodeRegisterQuery, encodeRegisterQuery, type RegisterSpec } from "./register/url-state";
export { csvCell, toCsv, type CsvColumn } from "./register/csv";
export {
  DEFAULT_PAGE_SIZE,
  PAGE_SIZES,
  type BulkAction,
  type FilterValue,
  type RegisterColumn,
  type RegisterFilter,
  type RegisterFilterOption,
  type RegisterPage,
  type RegisterQuery,
  type RegisterQueryResult,
  type SortDir,
  type Translate,
} from "./register/types";

// DESIGN-04: record detail pattern and feedback primitives.
export {
  RecordDetail,
  DEFAULT_RECORD_TABS,
  type RecordDetailProps,
  type RecordRail,
  type RecordStatus,
  type RecordTab,
} from "./patterns/RecordDetail";
export { WorkflowBar, type WorkflowAction, type WorkflowBarProps, type WorkflowStep } from "./patterns/WorkflowBar";
export { ConfirmProvider, confirm, useConfirm, type ConfirmOptions, type ConfirmProviderProps } from "./feedback/confirm";
export {
  Toaster,
  toast,
  TOAST_TIMEOUT_MS,
  MAX_VISIBLE_TOASTS,
  type ToastAction,
  type ToastOptions,
  type ToasterProps,
} from "./feedback/toast";
export {
  EmptyState,
  LoadingState,
  ErrorState,
  OfflineState,
  SyncConflictState,
  errorTermKey,
  requestErrorFrom,
  type EmptyStateProps,
  type ErrorStateProps,
  type LoadingStateProps,
  type OfflineStateProps,
  type RequestError,
  type StateAction,
  type SyncConflictStateProps,
} from "./feedback/states";
