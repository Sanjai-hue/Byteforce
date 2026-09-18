import {
  Background,
  Controls,
  MarkerType,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { GitBranch } from "lucide-react";
import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import {
  Badge,
  Card,
  CardBody,
  Code,
  Confidence,
  EmptyState,
  ErrorNotice,
  Spinner,
} from "@/components/ui";
import { api } from "@/services/api";
import { useAsync } from "@/hooks/useApi";
import type { GraphEdge, GraphNode } from "@/types/api";

/** Layer nodes by dependency depth so the graph reads left to right. */
function layout(nodes: GraphNode[], edges: GraphEdge[]): Node[] {
  const depth = new Map<string, number>();
  const incoming = new Map<string, string[]>();
  for (const edge of edges) {
    incoming.set(edge.source, [...(incoming.get(edge.source) ?? []), edge.target]);
  }

  const resolve = (id: string, seen: Set<string>): number => {
    if (depth.has(id)) return depth.get(id)!;
    if (seen.has(id)) return 0;
    seen.add(id);
    const parents = incoming.get(id) ?? [];
    const value = parents.length === 0 ? 0 : 1 + Math.max(...parents.map((p) => resolve(p, seen)));
    depth.set(id, value);
    return value;
  };

  const connected = nodes.filter((node) => node.connected);
  const isolated = nodes.filter((node) => !node.connected);
  for (const node of connected) resolve(node.id, new Set());

  const columns = new Map<number, number>();
  const positioned: Node[] = connected.map((node) => {
    const column = depth.get(node.id) ?? 0;
    const row = columns.get(column) ?? 0;
    columns.set(column, row + 1);
    return {
      id: node.id,
      position: { x: column * 260, y: row * 110 },
      data: { label: node.code },
      style: {
        width: 150,
        borderRadius: 12,
        border: "1px solid rgba(56, 189, 248, 0.4)",
        background: "#070e1b",
        color: "#ffffff",
        fontSize: 13,
        fontWeight: 600,
        padding: 10,
        boxShadow: "0 4px 20px rgba(0, 0, 0, 0.5), 0 0 12px rgba(56, 189, 248, 0.2)",
      },
    };
  });

  const isolatedStartColumn = Math.max(0, ...positioned.map((n) => n.position.x / 260)) + 1;
  isolated.forEach((node, index) => {
    positioned.push({
      id: node.id,
      position: { x: isolatedStartColumn * 260, y: index * 60 },
      data: { label: node.code },
      style: {
        width: 120,
        borderRadius: 10,
        border: "1px dashed rgba(255, 255, 255, 0.15)",
        background: "rgba(255, 255, 255, 0.03)",
        color: "#64748b",
        fontSize: 12,
        padding: 8,
      },
    });
  });

  return positioned;
}

export function Dependencies() {
  const { documentId = "" } = useParams();
  const { data, loading, error, refresh } = useAsync(
    () => api.getDependencies(documentId),
    [documentId],
  );
  const [selected, setSelected] = useState<string | null>(null);

  const nodes = useMemo(
    () => (data ? layout(data.nodes, data.edges) : []),
    [data],
  );

  const edges: Edge[] = useMemo(
    () =>
      (data?.edges ?? []).map((edge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        label: edge.relationship.replace(/_/g, " "),
        labelStyle: { fontSize: 10, fill: "#cbd5e1", fontWeight: 500 },
        labelBgStyle: { fill: "#0b1526", fillOpacity: 0.95 },
        labelBgPadding: [4, 2] as [number, number],
        labelBgBorderRadius: 4,
        style: { stroke: "rgba(56, 189, 248, 0.6)", strokeWidth: 1.5 },
        markerEnd: { type: MarkerType.ArrowClosed, color: "#38bdf8" },
      })),
    [data],
  );

  if (loading)
    return (
      <div className="flex items-center gap-3 py-20 text-sm text-slate-400">
        <Spinner /> Loading topological dependency graph…
      </div>
    );
  if (error) return <ErrorNotice message={error} onRetry={refresh} />;
  if (!data) return null;

  const selectedNode = data.nodes.find((node) => node.id === selected) ?? null;
  const outgoing = data.edges.filter((edge) => edge.source === selected);
  const incoming = data.edges.filter((edge) => edge.target === selected);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-sans text-2xl font-bold tracking-tight text-white">Dependency Graph</h1>
        <p className="mt-1 text-xs text-slate-400">
          {data.total_edges} relationship{data.total_edges === 1 ? "" : "s"} across{" "}
          {data.nodes.length} requirements. Click any node to inspect prerequisite chains.
        </p>
      </div>

      {data.total_edges === 0 ? (
        <EmptyState
          icon={<GitBranch className="size-6 text-emerald-400" />}
          title="No explicit dependencies reported"
          description="All requirements can proceed in decoupled implementation."
        />
      ) : (
        <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
          <Card className="overflow-hidden border-white/10 bg-[#070e1b]/80 shadow-2xl backdrop-blur-xl">
            <div className="reqguard-flow h-[580px]">
              <ReactFlow
                nodes={nodes}
                edges={edges}
                colorMode="dark"
                fitView
                minZoom={0.2}
                proOptions={{ hideAttribution: true }}
                onNodeClick={(_, node) => setSelected(node.id)}
                onPaneClick={() => setSelected(null)}
              >
                <Background color="rgba(148, 163, 184, 0.15)" gap={24} />
                <Controls showInteractive={false} />
              </ReactFlow>
            </div>
          </Card>

          <Card className="h-fit border-white/10 bg-[#070e1b]/80 backdrop-blur-xl">
            <CardBody className="p-5">
              {selectedNode ? (
                <div className="space-y-4">
                  <div className="flex items-center gap-2">
                    <Code>{selectedNode.code}</Code>
                    <Badge tone="neutral">
                      {selectedNode.requirement_type.replace("_", " ")}
                    </Badge>
                  </div>
                  <p className="text-xs leading-relaxed text-slate-200">{selectedNode.original_text}</p>
                  <p className="font-mono text-[10px] text-slate-500">
                    Source: {selectedNode.section ?? "General"}
                    {selectedNode.page_number ? ` · page ${selectedNode.page_number}` : ""}
                  </p>

                  <div className="border-t border-white/10 pt-3">
                    <p className="font-mono text-[10px] uppercase tracking-wider text-slate-400">
                      Depends on Prerequisite ({outgoing.length})
                    </p>
                    <ul className="mt-2 space-y-2">
                      {outgoing.length === 0 ? (
                        <li className="text-xs text-slate-500">None</li>
                      ) : (
                        outgoing.map((edge) => (
                          <li key={edge.id} className="rounded-xl border border-white/5 bg-white/[0.03] p-2.5">
                            <div className="flex items-center justify-between gap-2">
                              <Code>{edge.target_code}</Code>
                              <Confidence value={edge.confidence} />
                            </div>
                            {edge.reason ? (
                              <p className="mt-1 text-xs text-slate-400">{edge.reason}</p>
                            ) : null}
                          </li>
                        ))
                      )}
                    </ul>
                  </div>

                  <div className="border-t border-white/10 pt-3">
                    <p className="font-mono text-[10px] uppercase tracking-wider text-slate-400">
                      Blocks Downstream ({incoming.length})
                    </p>
                    <ul className="mt-2 space-y-2">
                      {incoming.length === 0 ? (
                        <li className="text-xs text-slate-500">None</li>
                      ) : (
                        incoming.map((edge) => (
                          <li key={edge.id} className="rounded-xl border border-white/5 bg-white/[0.03] p-2.5">
                            <div className="flex items-center justify-between gap-2">
                              <Code>{edge.source_code}</Code>
                              <Confidence value={edge.confidence} />
                            </div>
                            {edge.reason ? (
                              <p className="mt-1 text-xs text-slate-400">{edge.reason}</p>
                            ) : null}
                          </li>
                        ))
                      )}
                    </ul>
                  </div>
                </div>
              ) : (
                <div className="text-center py-6">
                  <GitBranch className="mx-auto size-8 text-sky-400/40 mb-2" />
                  <p className="text-xs text-slate-400">
                    Select a node in the graph to inspect bidirectional prerequisite & blocking dependencies.
                  </p>
                </div>
              )}
            </CardBody>
          </Card>
        </div>
      )}
    </div>
  );
}
