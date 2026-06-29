export const BLUEPRINT_SECTIONS = [
  {
    id: 'mvp_scope',
    label: 'MVP Scope',
    shortLabel: 'MVP',
    aliases: ['action_items'],
    headings: ['MVP Definition', 'Implementation Roadmap'],
  },
  {
    id: 'business_plan',
    label: 'Business Plan',
    shortLabel: 'Business',
    aliases: ['pitch_script'],
    headings: ['Business Model'],
  },
  {
    id: 'technical_architecture',
    label: 'Technical Architecture',
    shortLabel: 'Technical',
    aliases: [],
    headings: ['Technical Architecture'],
  },
  {
    id: 'ux_strategy',
    label: 'UX Strategy',
    shortLabel: 'UX',
    aliases: [],
    headings: ['UX Strategy'],
  },
  {
    id: 'go_to_market',
    label: 'Go-To-Market',
    shortLabel: 'GTM',
    aliases: ['marketing_strategy'],
    headings: ['Marketing Strategy'],
  },
  {
    id: 'risk_assessment',
    label: 'Risk Assessment',
    shortLabel: 'Risk',
    aliases: [],
    headings: ['Risk Assessment'],
  },
  {
    id: 'financial_plan',
    label: 'Financial Plan',
    shortLabel: 'Financial',
    aliases: ['financial_projection'],
    headings: ['Financial Analysis'],
  },
];

const SECTION_ALIAS_MAP = BLUEPRINT_SECTIONS.reduce((acc, section) => {
  acc[section.id] = section.id;
  section.aliases.forEach((alias) => {
    acc[alias] = section.id;
  });
  return acc;
}, {});

export function normalizeBlueprintSectionKey(key) {
  const normalized = String(key || '').trim().toLowerCase().replace(/[\s-]+/g, '_');
  return SECTION_ALIAS_MAP[normalized] || normalized;
}

export function getSectionContent(sessionDetails, sectionId) {
  const sections = sessionDetails?.sections || {};
  const section = BLUEPRINT_SECTIONS.find((item) => item.id === sectionId);
  const candidateKeys = [sectionId, ...(section?.aliases || [])];

  for (const key of candidateKeys) {
    const value = extractContent(sections[key]);
    if (value) return value;
  }

  return getFinalReportSectionContent(sessionDetails, sectionId);
}

export function countGeneratedSections(sessionDetails) {
  return BLUEPRINT_SECTIONS.filter((section) => getSectionContent(sessionDetails, section.id)).length;
}

export function extractContent(value) {
  if (!value) return '';
  if (typeof value === 'string') return value.trim();
  if (typeof value === 'object') {
    if (typeof value.content === 'string') return value.content.trim();
    if (typeof value.text === 'string') return value.text.trim();
    return JSON.stringify(value, null, 2);
  }
  return String(value).trim();
}

export function mergeBlueprintSection(sections, rawKey, rawAfter) {
  const key = normalizeBlueprintSectionKey(rawKey);
  const nextContent = extractContent(rawAfter);
  const previous = sections?.[key] || {};
  const previousContent = extractContent(previous);
  const next = typeof rawAfter === 'object' && rawAfter !== null ? rawAfter : { content: nextContent };

  if (!nextContent && previousContent) {
    return {
      ...sections,
      [key]: {
        ...next,
        content: previousContent,
        status: previous.status || next.status || 'draft',
        source: previous.source || next.source || 'previous',
      },
    };
  }

  return {
    ...sections,
    [key]: next,
  };
}

function getFinalReportSectionContent(sessionDetails, sectionId) {
  const section = BLUEPRINT_SECTIONS.find((item) => item.id === sectionId);
  if (!section) return '';

  const reportText = getFinalReportText(sessionDetails);
  if (!reportText) return '';

  for (const heading of section.headings) {
    const body = extractMarkdownHeading(reportText, heading);
    if (body) return body;
  }

  return '';
}

function getFinalReportText(sessionDetails) {
  if (typeof sessionDetails?.summary === 'string' && sessionDetails.summary.trim()) {
    return sessionDetails.summary;
  }

  const decisions = Array.isArray(sessionDetails?.decision_log) ? sessionDetails.decision_log : [];
  for (let index = decisions.length - 1; index >= 0; index -= 1) {
    const summary = decisions[index]?.summary;
    if (typeof summary === 'string' && summary.trim()) return summary;
  }

  return '';
}

function extractMarkdownHeading(markdown, heading) {
  const escaped = heading.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const regex = new RegExp(`^#\\s+${escaped}\\s*$`, 'im');
  const match = regex.exec(markdown);
  if (!match) return '';

  const rest = markdown.slice(match.index + match[0].length);
  const nextHeading = rest.search(/^#\s+/m);
  const body = (nextHeading >= 0 ? rest.slice(0, nextHeading) : rest).trim();
  if (!body || body === 'Insufficient information from the discussion.') return '';
  return body;
}
