import {
  Badge,
  Button,
  Checkbox,
  Combobox,
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  FormField,
  Icon,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Spinner,
  StatusChip,
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@aip/ui";

/**
 * DESIGN-01 dev-only fixture: renders every @aip/ui component for the Playwright axe run.
 * Loaded lazily by router.ts only when `!import.meta.env.PROD`, so production bundles omit it.
 * Fixture strings are test data, not product labels, so they are not terminology keys.
 */

const options = [
  { value: "draft", label: "Draft" },
  { value: "approved", label: "Approved" },
];

export function UiFixture() {
  return (
    <TooltipProvider>
      <main data-testid="ui-fixture">
        <h1>{"UI fixture"}</h1>
        <section aria-label="Buttons and badges">
          <Button>{"Save"}</Button> <Button variant="secondary">{"Cancel"}</Button> <Badge tone="accent">{"New"}</Badge>{" "}
          <StatusChip tone="danger" icon="alert" label="Rejected" /> <StatusChip tone="success" icon="success" label="Approved" />{" "}
          <Spinner label="Loading" /> <Icon name="info" label="Information" />
        </section>
        <section aria-label="Form controls">
          <FormField label="Name" hint="As on the permit">
            {(control) => <Input {...control} />}
          </FormField>
          <Checkbox id="fx-agree" /> <Label htmlFor="fx-agree">{"I agree"}</Label>
          <Select>
            <SelectTrigger aria-label="Status">
              <SelectValue placeholder="Choose" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="draft">{"Draft"}</SelectItem>
            </SelectContent>
          </Select>
          <Combobox options={options} aria-label="Workflow state" />
        </section>
        <section aria-label="Overlays">
          <Dialog>
            <DialogTrigger asChild>
              <Button>{"Open dialog"}</Button>
            </DialogTrigger>
            <DialogContent closeLabel="Close">
              <DialogTitle>{"Dialog title"}</DialogTitle>
              <DialogDescription>{"Dialog body"}</DialogDescription>
              <DialogClose asChild>
                <Button>{"Done"}</Button>
              </DialogClose>
            </DialogContent>
          </Dialog>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="secondary">{"Actions"}</Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent>
              <DropdownMenuLabel>{"Item"}</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem>{"Edit"}</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="secondary">{"Hover me"}</Button>
            </TooltipTrigger>
            <TooltipContent>{"Tooltip text"}</TooltipContent>
          </Tooltip>
        </section>
        <Table>
          <TableCaption>{"Fixture table"}</TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead>{"Code"}</TableHead>
              <TableHead>{"Status"}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow>
              <TableCell>{"P-001"}</TableCell>
              <TableCell>
                <StatusChip tone="warning" icon="warning" label="Pending" />
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </main>
    </TooltipProvider>
  );
}
