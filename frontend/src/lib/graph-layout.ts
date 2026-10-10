import dagre from 'dagre';
import type { StepDefinition, WorkflowDefinition } from '../types';

export type NodeType = 'trigger' | 'action' | 'branch' | 'delay' | 'wait_for_event' | 'end';

export interface GraphNode {
  id: string;
  type: NodeType;
  label: string;
  sublabel?: string;
  /** Centre of the node. */
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface GraphPoint {
  x: number;
  y: number;
}

export interface GraphEdge {
  points: GraphPoint[];
  /** "true" or "false" on the two outgoing edges of a branch. */
  label?: string;
}

export interface GraphLayout {
  nodes: GraphNode[];
  edges: GraphEdge[];
  width: number;
  height: number;
}

const TRIGGER_ID = '__trigger__';
const END_ID = '__end__';

// WorkflowGraph.tsx makes the SVG viewBox 20px larger than the layout on every side but starts it at 0,0,
// so everything is shifted by the same amount here to keep the padding even on all four sides.
const PADDING = 20;

const STEP_SIZE = { width: 170, height: 46 };
const END_SIZE = { width: 72, height: 32 };

function describeCondition(step: Extract<StepDefinition, { type: 'branch' }>): string {
  const { field, operator, value } = step.condition ?? { field: '', operator: '' };
  if (value === undefined) return `${field} ${operator}`.trim();
  const shown = typeof value === 'string' ? value : JSON.stringify(value);
  return `${field} ${operator} ${shown}`.trim();
}

function describeStep(step: StepDefinition): { type: NodeType; sublabel?: string } {
  switch (step.type) {
    case 'branch':
      return { type: 'branch', sublabel: describeCondition(step) };
    case 'delay':
      return { type: 'delay', sublabel: `wait ${step.duration_seconds}s` };
    case 'wait_for_event':
      return {
        type: 'wait_for_event',
        sublabel: step.timeout_seconds ? `${step.event_name} (timeout ${step.timeout_seconds}s)` : step.event_name,
      };
    default:
      return { type: 'action', sublabel: [step.connector_id, step.action_id].filter(Boolean).join('.') };
  }
}

function targetsOf(step: StepDefinition): { to: string | undefined; label?: string }[] {
  if (step.type === 'branch') {
    return [
      { to: step.on_true, label: 'true' },
      { to: step.on_false, label: 'false' },
    ];
  }
  return [{ to: step.next }];
}

/**
 * Lays out a workflow definition top to bottom: trigger, then every step, then a shared "end" node when any
 * step points at it. Edges that point at a step that does not exist are left out instead of throwing, so the
 * preview keeps working while a draft is still incomplete.
 */
export function layoutWorkflow(definition: WorkflowDefinition): GraphLayout {
  const steps = definition?.steps ?? {};
  const g = new dagre.graphlib.Graph({ multigraph: true });
  g.setGraph({ rankdir: 'TB', nodesep: 40, ranksep: 56, marginx: 0, marginy: 0 });
  g.setDefaultEdgeLabel(() => ({}));

  const meta = new Map<string, Omit<GraphNode, 'x' | 'y'>>();
  const addNode = (id: string, type: NodeType, label: string, sublabel?: string, size = STEP_SIZE) => {
    meta.set(id, { id, type, label, sublabel, width: size.width, height: size.height });
    g.setNode(id, { width: size.width, height: size.height });
  };

  const trigger = definition?.trigger;
  addNode(
    TRIGGER_ID,
    'trigger',
    'Trigger',
    trigger ? [trigger.connector_id, trigger.trigger_id].filter(Boolean).join('.') : undefined,
  );
  for (const [key, step] of Object.entries(steps)) {
    const { type, sublabel } = describeStep(step);
    addNode(key, type, key, sublabel);
  }

  const resolve = (name: string | undefined): string | null => {
    if (!name) return null;
    if (name === 'end') {
      if (!meta.has(END_ID)) addNode(END_ID, 'end', 'End', undefined, END_SIZE);
      return END_ID;
    }
    return meta.has(name) ? name : null;
  };

  const start = resolve(definition?.start_at);
  if (start) g.setEdge(TRIGGER_ID, start, {}, 'start');
  for (const [key, step] of Object.entries(steps)) {
    for (const { to, label } of targetsOf(step)) {
      const target = resolve(to);
      if (target) g.setEdge(key, target, {}, label ?? 'next');
    }
  }

  dagre.layout(g);

  const nodes: GraphNode[] = [...meta.values()].map((m) => {
    const placed = g.node(m.id);
    return { ...m, x: placed.x + PADDING, y: placed.y + PADDING };
  });
  const edges: GraphEdge[] = g.edges().map((e) => {
    const label = e.name === 'true' || e.name === 'false' ? e.name : undefined;
    const points = (g.edge(e).points ?? []).map((pt) => ({ x: pt.x + PADDING, y: pt.y + PADDING }));
    return { points, label };
  });
  const graph = g.graph();
  return { nodes, edges, width: graph.width ?? 0, height: graph.height ?? 0 };
}
