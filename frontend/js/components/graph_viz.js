// Cytoscape.js wrapper for entity-relation graph visualisation.
// Cytoscape is loaded globally from CDN (see index.html).

const TYPE_COLOR = {
  Person:       '#6366f1',
  Organization: '#0ea5e9',
  Project:      '#10b981',
  Location:     '#f59e0b',
  Document:     '#8b5cf6',
  Concept:      '#ec4899',
  Event:        '#ef4444',
  Unknown:      '#94a3b8',
};

export function colorForType(type) {
  return TYPE_COLOR[type] || TYPE_COLOR.Unknown;
}

export function knownTypes() {
  return Object.keys(TYPE_COLOR).filter(t => t !== 'Unknown');
}

export function renderGraph(container, { nodes, edges }, { onNodeClick } = {}) {
  if (typeof cytoscape === 'undefined') {
    container.textContent = 'Cytoscape.js non chargé.';
    return null;
  }
  const cy = cytoscape({
    container,
    elements: [
      ...nodes.map(n => ({
        data: { id: n.id, label: n.label, type: n.type },
      })),
      ...edges.map((e, i) => ({
        data: {
          id: `e_${i}_${e.source}_${e.target}`,
          source: e.source,
          target: e.target,
          label: e.type,
          valid_from: e.valid_from,
          valid_to: e.valid_to,
        },
      })),
    ],
    style: [
      {
        selector: 'node',
        style: {
          'background-color': (ele) => colorForType(ele.data('type')),
          'label': 'data(label)',
          'color': '#1f2937',
          'font-size': 11,
          'text-valign': 'bottom',
          'text-margin-y': 6,
          'text-wrap': 'ellipsis',
          'text-max-width': 120,
          'width': 18,
          'height': 18,
          'border-color': '#fff',
          'border-width': 1.5,
        },
      },
      {
        selector: 'edge',
        style: {
          'curve-style': 'bezier',
          'width': 1.2,
          'line-color': '#cbd5e1',
          'target-arrow-color': '#cbd5e1',
          'target-arrow-shape': 'triangle',
          'arrow-scale': 0.8,
          'opacity': 0.85,
        },
      },
      {
        selector: ':selected',
        style: {
          'background-color': '#6366f1',
          'border-color': '#4f46e5',
          'border-width': 2,
          'line-color': '#6366f1',
          'target-arrow-color': '#6366f1',
        },
      },
    ],
    layout: {
      name: 'cose',
      animate: false,
      padding: 30,
      nodeRepulsion: 4500,
      idealEdgeLength: 90,
      gravity: 0.2,
    },
    minZoom: 0.2,
    maxZoom: 4,
  });

  if (onNodeClick) {
    cy.on('tap', 'node', (evt) => onNodeClick(evt.target.data()));
  }
  return cy;
}
