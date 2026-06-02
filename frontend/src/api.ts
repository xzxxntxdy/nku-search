export type SearchHit = {
  doc_id: string;
  url: string;
  title: string;
  snippet: string;
  score: number;
  pagerank: number;
  filetype: string;
  section: string;
  category: string;
  fetched_at: string;
  snapshot_path: string;
  matched_terms: string[];
  explanation: Record<string, number | string>;
};

export type SearchResponse = {
  query: string;
  mode: string;
  total: number;
  diagnostics: {
    backend: string;
    took_ms: number;
    total_candidates: number;
    total_matches: number;
    facets: Array<{ name: string; buckets: Record<string, number> }>;
  } | null;
  results: SearchHit[];
};

export type StatsResponse = {
  backend: string;
  documents: number;
  vocabulary: number | null;
  schema: Array<{ name: string; field_type: string; boost: number; indexed: boolean; stored: boolean; scorable: boolean }>;
  facets: Array<{ name: string; buckets: Record<string, number> }>;
  crawl_plan?: TopicResponse;
  features: string[];
  diagnostics?: unknown;
};

export type TopicSection = {
  key: string;
  label: string;
  category: string;
  description: string;
  seed_urls: string[];
  allowed_domains: string[];
  max_pages: number;
  scaled_max_pages: number;
  priority: number;
  depth_limit: number;
  politeness_delay: number;
  concurrency_per_domain: number;
  document_first: boolean;
  seed_count: number;
  indexed_count: number;
  indexed_progress: number;
};

export type TopicResponse = {
  minimum_pages: number;
  target_pages: number;
  section_count: number;
  seed_count: number;
  sections: TopicSection[];
  categories: Array<{ name: string; indexed_count: number }>;
};

export type HistoryRow = {
  id: number;
  query: string;
  mode: string;
  site?: string;
  filetype?: string;
  result_count: number;
  created_at: string;
};

export async function apiGet<T>(url: string): Promise<T> {
  const response = await fetch(url, { credentials: 'include' });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export async function apiPost<T>(url: string, body?: unknown): Promise<T> {
  const response = await fetch(url, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  if (!response.ok) {
    const text = await response.text();
    let message = text || `${response.status} ${response.statusText}`;
    try {
      const data = JSON.parse(text) as { message?: string };
      message = data.message || message;
    } catch {
      // Keep the raw response text for non-JSON errors.
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}
