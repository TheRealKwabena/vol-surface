import { Sigma } from "lucide-react";
import { GreeksTab } from "@/components/greeks-tab";
import { ThemeToggle } from "@/components/theme-toggle";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { VolSurfaceTab } from "@/components/vol-surface-tab";

export default function Home() {
  return (
    <div className="flex min-h-full flex-col">
      <header className="border-b border-border/70 bg-card/60 backdrop-blur-sm">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-4 px-6 py-5">
          <div className="flex items-center gap-3">
            <div className="flex size-10 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm">
              <Sigma className="size-5" />
            </div>
            <div>
              <h1 className="text-lg font-semibold tracking-tight">Vol Surface &amp; Greeks Visualizer</h1>
              <p className="text-xs text-muted-foreground">Forward-implied IV surface · closed-form Greeks</p>
            </div>
          </div>
          <ThemeToggle />
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-6 px-6 py-8">
        <Tabs defaultValue="surface">
          <TabsList>
            <TabsTrigger value="surface">Vol Surface (live data)</TabsTrigger>
            <TabsTrigger value="greeks">Greeks Explorer (no data needed)</TabsTrigger>
          </TabsList>
          <TabsContent value="surface">
            <VolSurfaceTab />
          </TabsContent>
          <TabsContent value="greeks">
            <GreeksTab />
          </TabsContent>
        </Tabs>
      </main>
    </div>
  );
}
