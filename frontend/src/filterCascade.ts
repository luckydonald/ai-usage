import type { Filters, FunnelBranch } from "./types";

interface FilterIndex {
  allServices: string[];
  allProviders: string[];
  allAccounts: string[];
  allMetrics: string[];
  providersByService: Map<string, Set<string>>;
  servicesByProvider: Map<string, Set<string>>;
  accountsByProvider: Map<string, Set<string>>;
  accountProvider: Map<string, string>;
  accountService: Map<string, string>;
  accountMetrics: Map<string, Set<string>>;
  metricAccounts: Map<string, Set<string>>;
}

function addToSetMap(map: Map<string, Set<string>>, key: string, value: string): void {
  const set = map.get(key) ?? new Set<string>();
  set.add(value);
  map.set(key, set);
}

// Provider/metric identity is name-only/global here, matching how `sankey.ts` dedupes its nodes
// (a provider name or metric_key can be reached from more than one branch/account) — so the
// index is built by walking every branch, not scoped to a single one.
function buildFilterIndex(tree: FunnelBranch[]): FilterIndex {
  const providersByService = new Map<string, Set<string>>();
  const servicesByProvider = new Map<string, Set<string>>();
  const accountsByProvider = new Map<string, Set<string>>();
  const accountProvider = new Map<string, string>();
  const accountService = new Map<string, string>();
  const accountMetrics = new Map<string, Set<string>>();
  const metricAccounts = new Map<string, Set<string>>();
  const allServices = new Set<string>();
  const allProviders = new Set<string>();
  const allAccounts = new Set<string>();
  const allMetrics = new Set<string>();

  for (const branch of tree) {
    allServices.add(branch.service);
    for (const providerNode of branch.providers) {
      allProviders.add(providerNode.provider);
      addToSetMap(providersByService, branch.service, providerNode.provider);
      addToSetMap(servicesByProvider, providerNode.provider, branch.service);
      for (const accountNode of providerNode.accounts) {
        allAccounts.add(accountNode.id);
        addToSetMap(accountsByProvider, providerNode.provider, accountNode.id);
        accountProvider.set(accountNode.id, providerNode.provider);
        accountService.set(accountNode.id, branch.service);
        for (const metric of accountNode.metrics) {
          allMetrics.add(metric.key);
          addToSetMap(accountMetrics, accountNode.id, metric.key);
          addToSetMap(metricAccounts, metric.key, accountNode.id);
        }
      }
    }
  }

  return {
    allServices: [...allServices],
    allProviders: [...allProviders],
    allAccounts: [...allAccounts],
    allMetrics: [...allMetrics],
    providersByService,
    servicesByProvider,
    accountsByProvider,
    accountProvider,
    accountService,
    accountMetrics,
    metricAccounts,
  };
}

function union(list: string[], extra: Iterable<string>): string[] {
  const set = new Set(list);
  for (const value of extra) set.add(value);
  return [...set];
}

// Only pulls in an account's metrics when the account would otherwise show nothing — if it
// already has at least one of its own metric keys active, something already displays, so we
// don't force-expand the user's (possibly intentionally narrow) metric selection.
function smartEnableAccountMetrics(index: FilterIndex, metrics: string[], accountId: string): string[] {
  const ownMetrics = index.accountMetrics.get(accountId) ?? new Set<string>();
  if ([...ownMetrics].some((key) => metrics.includes(key))) return metrics;
  return union(metrics, ownMetrics);
}

// Every catalog value in every dimension — the new "show everything" default, since empty lists
// no longer mean "unrestricted" (they now mean "nothing", see `pruneOrphans`).
export function defaultFilters(tree: FunnelBranch[]): Filters {
  const index = buildFilterIndex(tree);
  return { services: index.allServices, providers: index.allProviders, accounts: index.allAccounts, metrics: index.allMetrics };
}

function enableService(index: FilterIndex, filters: Filters, service: string): Filters {
  const providers = index.providersByService.get(service) ?? new Set<string>();
  const accounts = new Set<string>();
  for (const provider of providers) for (const account of index.accountsByProvider.get(provider) ?? []) accounts.add(account);
  const metrics = new Set<string>();
  for (const account of accounts) for (const key of index.accountMetrics.get(account) ?? []) metrics.add(key);
  // Selecting a whole service is a big, explicit action — force-enable everything reachable
  // under it unconditionally, including metrics (no smart per-account check at this level).
  return {
    services: union(filters.services, [service]),
    providers: union(filters.providers, providers),
    accounts: union(filters.accounts, accounts),
    metrics: union(filters.metrics, metrics),
  };
}

function enableProvider(index: FilterIndex, filters: Filters, provider: string): Filters {
  const services = index.servicesByProvider.get(provider) ?? new Set<string>();
  const accounts = index.accountsByProvider.get(provider) ?? new Set<string>();
  let metrics = filters.metrics;
  for (const account of accounts) metrics = smartEnableAccountMetrics(index, metrics, account);
  return {
    services: union(filters.services, services),
    providers: union(filters.providers, [provider]),
    accounts: union(filters.accounts, accounts),
    metrics,
  };
}

function enableAccount(index: FilterIndex, filters: Filters, accountId: string): Filters {
  const provider = index.accountProvider.get(accountId);
  const service = index.accountService.get(accountId);
  return {
    services: service ? union(filters.services, [service]) : filters.services,
    providers: provider ? union(filters.providers, [provider]) : filters.providers,
    accounts: union(filters.accounts, [accountId]),
    metrics: smartEnableAccountMetrics(index, filters.metrics, accountId),
  };
}

function enableMetric(index: FilterIndex, filters: Filters, metricKey: string): Filters {
  const qualifyingAccounts = index.metricAccounts.get(metricKey) ?? new Set<string>();
  const metrics = union(filters.metrics, [metricKey]);
  const alreadyDisplayed = [...qualifyingAccounts].some((account) => filters.accounts.includes(account));
  if (alreadyDisplayed) return { ...filters, metrics };

  const providers = new Set<string>();
  const services = new Set<string>();
  for (const account of qualifyingAccounts) {
    const provider = index.accountProvider.get(account);
    const service = index.accountService.get(account);
    if (provider) providers.add(provider);
    if (service) services.add(service);
  }
  return {
    services: union(filters.services, services),
    providers: union(filters.providers, providers),
    accounts: union(filters.accounts, qualifyingAccounts),
    metrics,
  };
}

function sameSize(a: Filters, b: Filters): boolean {
  return a.services.length === b.services.length && a.providers.length === b.providers.length && a.accounts.length === b.accounts.length && a.metrics.length === b.metrics.length;
}

// Repeatedly drops any explicitly-listed value that has zero remaining active neighbors in its
// immediately adjacent column(s), until a full pass changes nothing. An empty adjacent list means
// zero neighbors are active (no more "empty = unrestricted" special case), so a fully-cleared
// column correctly ripples out and clears everything connected to it.
function pruneOrphans(index: FilterIndex, filters: Filters): Filters {
  let current = filters;
  for (;;) {
    const services = current.services.filter((service) => [...(index.providersByService.get(service) ?? [])].some((provider) => current.providers.includes(provider)));
    const providers = current.providers.filter(
      (provider) =>
        [...(index.servicesByProvider.get(provider) ?? [])].some((service) => current.services.includes(service)) &&
        [...(index.accountsByProvider.get(provider) ?? [])].some((account) => current.accounts.includes(account)),
    );
    const accounts = current.accounts.filter((account) => {
      const provider = index.accountProvider.get(account);
      return (provider ? current.providers.includes(provider) : false) && [...(index.accountMetrics.get(account) ?? [])].some((key) => current.metrics.includes(key));
    });
    const metrics = current.metrics.filter((key) => [...(index.metricAccounts.get(key) ?? [])].some((account) => current.accounts.includes(account)));

    const next: Filters = { services, providers, accounts, metrics };
    if (sameSize(next, current)) return next;
    current = next;
  }
}

function disable(index: FilterIndex, filters: Filters, dimension: keyof Filters, value: string): Filters {
  return pruneOrphans(index, { ...filters, [dimension]: filters[dimension].filter((entry) => entry !== value) });
}

export function toggleService(tree: FunnelBranch[], filters: Filters, service: string): Filters {
  const index = buildFilterIndex(tree);
  return filters.services.includes(service) ? disable(index, filters, "services", service) : enableService(index, filters, service);
}

export function toggleProvider(tree: FunnelBranch[], filters: Filters, provider: string): Filters {
  const index = buildFilterIndex(tree);
  return filters.providers.includes(provider) ? disable(index, filters, "providers", provider) : enableProvider(index, filters, provider);
}

export function toggleAccount(tree: FunnelBranch[], filters: Filters, accountId: string): Filters {
  const index = buildFilterIndex(tree);
  return filters.accounts.includes(accountId) ? disable(index, filters, "accounts", accountId) : enableAccount(index, filters, accountId);
}

export function toggleMetric(tree: FunnelBranch[], filters: Filters, metricKey: string): Filters {
  const index = buildFilterIndex(tree);
  return filters.metrics.includes(metricKey) ? disable(index, filters, "metrics", metricKey) : enableMetric(index, filters, metricKey);
}
