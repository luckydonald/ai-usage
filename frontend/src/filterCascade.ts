import type { Filters, SankeyAccount, SankeyOrganization, SankeyParser, SankeyService } from "./types";

function unique(values: Iterable<string>): string[] {
  return [...new Set(values)];
}

function parserIds(parsers: SankeyParser[]): string[] {
  return parsers.map((parser) => parser.id);
}

function organizationParserIds(organization: SankeyOrganization): string[] {
  return parserIds(organization.parsers);
}

function accountParserIds(account: SankeyAccount): string[] {
  return unique(account.organizations.flatMap(organizationParserIds));
}

function serviceParserIds(service: SankeyService): string[] {
  return unique(service.accounts.flatMap(accountParserIds));
}

function allParsers(tree: SankeyService[]): SankeyParser[] {
  return tree.flatMap((service) => service.accounts.flatMap((account) => account.organizations.flatMap((organization) => organization.parsers)));
}

function toggleValues(filters: Filters, ids: string[]): Filters {
  const selected = new Set(filters.accounts);
  const allSelected = ids.every((id) => selected.has(id));
  for (const id of ids) {
    if (allSelected) selected.delete(id);
    else selected.add(id);
  }
  return { ...filters, accounts: [...selected] };
}

export function defaultFilters(tree: SankeyService[]): Filters {
  return {
    accounts: allParsers(tree).map((parser) => parser.id),
    metrics: unique(allParsers(tree).flatMap((parser) => parser.metrics.map((metric) => metric.key))),
  };
}

export function toggleService(filters: Filters, service: SankeyService): Filters {
  return toggleValues(filters, serviceParserIds(service));
}

export function toggleAccount(filters: Filters, account: SankeyAccount): Filters {
  return toggleValues(filters, accountParserIds(account));
}

export function toggleOrganization(filters: Filters, organization: SankeyOrganization): Filters {
  return toggleValues(filters, organizationParserIds(organization));
}

export function toggleParser(filters: Filters, parser: SankeyParser): Filters {
  return toggleValues(filters, [parser.id]);
}

export function toggleMetric(filters: Filters, metricKey: string): Filters {
  const metrics = filters.metrics.includes(metricKey)
    ? filters.metrics.filter((key) => key !== metricKey)
    : [...filters.metrics, metricKey];
  return { ...filters, metrics };
}
