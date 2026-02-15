import { useMemo } from 'react';
import { layoutWorkflow, type GraphNode, type GraphEdge, type NodeType } from '../lib/graph-layout';
import type { WorkflowDefinition } from '../types';

const NODE_COLORS: Record<NodeType, { bg: string; border: string; text: string }> = {
  trigger:        { bg: '#dcfce7', border: '#22c55e', text: '#166534' },
  action:         { bg: '#dbeafe', border: '#3b82f6', text: '#1e40af' },
  branch:         { bg: '#fef9c3', border: '#eab308', text: '#854d0e' },
  delay:          { bg: '#f3e8ff', border: '#a855f7', text: '#6b21a8' },
  wait_for_event: { bg: '#ffedd5', border: '#f97316', text: '#9a3412' },
  end:            { bg: '#f3f4f6', border: '#9ca3af', text: '#374151' },
};

interface WorkflowGraphProps {
  definition: WorkflowDefinition;
  className?: string;
}

export function WorkflowGraph({ definition, className }: WorkflowGraphProps) {
  const layout = useMemo(() => layoutWorkflow(definition), [definition]);

  const padding = 20;
  const viewWidth = layout.width + padding * 2;
  const viewHeight = layout.height + padding * 2;

  return (
    <div className={`overflow-auto bg-white border border-gray-200 rounded ${className ?? ''}`}>
      <svg
        width="100%"
        viewBox={`0 0 ${viewWidth} ${viewHeight}`}
        style={{ minHeight: 200, maxHeight: 600 }}
      >
        <defs>
          <marker
            id="arrowhead"
            markerWidth="10"
            markerHeight="7"
            refX="10"
            refY="3.5"
            orient="auto"
          >
            <polygon points="0 0, 10 3.5, 0 7" fill="#9ca3af" />
          </marker>
        </defs>

        {layout.edges.map((edge, i) => (
          <EdgePath key={i} edge={edge} />
        ))}

        {layout.nodes.map((node) => (
          <NodeRect key={node.id} node={node} />
        ))}
      </svg>
    </div>
  );
}

function NodeRect({ node }: { node: GraphNode }) {
  const colors = NODE_COLORS[node.type];
  const rx = node.type === 'end' ? node.height / 2 : 6;

  return (
    <g>
      <rect
        x={node.x - node.width / 2}
        y={node.y - node.height / 2}
        width={node.width}
        height={node.height}
        rx={rx}
        fill={colors.bg}
        stroke={colors.border}
        strokeWidth={1.5}
      />
      <text
        x={node.x}
        y={node.sublabel ? node.y - 5 : node.y + 4}
        textAnchor="middle"
        fontSize={12}
        fontWeight={600}
        fill={colors.text}
      >
        {node.label}
      </text>
      {node.sublabel && (
        <text
          x={node.x}
          y={node.y + 12}
          textAnchor="middle"
          fontSize={9}
          fill="#6b7280"
        >
          {node.sublabel.length > 28 ? node.sublabel.slice(0, 26) + '...' : node.sublabel}
        </text>
      )}
    </g>
  );
}

function EdgePath({ edge }: { edge: GraphEdge }) {
  if (edge.points.length < 2) return null;

  const d = edge.points.length === 2
    ? `M ${edge.points[0].x} ${edge.points[0].y} L ${edge.points[1].x} ${edge.points[1].y}`
    : edge.points.reduce((acc, pt, i) => {
        if (i === 0) return `M ${pt.x} ${pt.y}`;
        if (i === 1 && edge.points.length === 3) return acc + ` Q ${pt.x} ${pt.y}`;
        if (i === edge.points.length - 1 && edge.points.length === 3) return acc + ` ${pt.x} ${pt.y}`;
        return acc + ` L ${pt.x} ${pt.y}`;
      }, '');

  const midIdx = Math.floor(edge.points.length / 2);
  const midPoint = edge.points[midIdx];

  return (
    <g>
      <path
        d={d}
        fill="none"
        stroke="#9ca3af"
        strokeWidth={1.5}
        markerEnd="url(#arrowhead)"
      />
      {edge.label && (
        <>
          <rect
            x={midPoint.x - 14}
            y={midPoint.y - 8}
            width={28}
            height={16}
            rx={3}
            fill="white"
          />
          <text
            x={midPoint.x}
            y={midPoint.y + 4}
            textAnchor="middle"
            fontSize={10}
            fill={edge.label === 'true' ? '#22c55e' : '#ef4444'}
            fontWeight={600}
          >
            {edge.label}
          </text>
        </>
      )}
    </g>
  );
}
