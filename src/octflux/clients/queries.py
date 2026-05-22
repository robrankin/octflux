"""GraphQL query documents, validated against the live Kraken schema 2026-05-21."""

from __future__ import annotations

# Account meter ids (Kraken internal) + postcode, to enrich the REST account.
ACCOUNT_META = """
query AccountMeta($accountNumber: String!) {
  account(accountNumber: $accountNumber) {
    properties {
      postcode
      electricityMeterPoints { mpan meters { id serialNumber } }
      gasMeterPoints { mprn meters { id serialNumber } }
    }
  }
}
""".strip()

ACCOUNT_BALANCE = """
query AccountBalance($accountNumber: String!) {
  account(accountNumber: $accountNumber) { balance }
}
""".strip()

ACCOUNT_TRANSACTIONS = """
query AccountTransactions($accountNumber: String!, $first: Int!, $after: String) {
  account(accountNumber: $accountNumber) {
    transactions(first: $first, after: $after) {
      pageInfo { hasNextPage endCursor }
      edges { node { id __typename postedDate createdAt amount balanceCarriedForward isCredit title } }
    }
  }
}
""".strip()

DISPATCHES = """
query Dispatches($accountNumber: String!) {
  plannedDispatches(accountNumber: $accountNumber) { start end delta meta { source location } }
  completedDispatches(accountNumber: $accountNumber) { start end delta meta { source location } }
}
""".strip()

CARBON_INTENSITY = """
query Carbon($postcode: String!) {
  getProjectedRegionalCarbonIntensity(postcode: $postcode) {
    projectedRegionalCarbonIntensity { periodStart value index }
  }
}
""".strip()

STATEMENTS = """
query Statements($accountNumber: String!, $first: Int!, $after: String) {
  account(accountNumber: $accountNumber) {
    bills(first: $first, after: $after) {
      pageInfo { hasNextPage endCursor }
      edges { node {
        id __typename
        ... on StatementType { fromDate toDate issuedDate closingBalance }
      } }
    }
  }
}
""".strip()

ELECTRICITY_METER_READINGS = """
query ElecReadings($accountNumber: String!, $meterId: String!, $first: Int!, $after: String) {
  electricityMeterReadings(accountNumber: $accountNumber, meterId: $meterId, first: $first, after: $after) {
    pageInfo { hasNextPage endCursor }
    edges { node { readAt source readingType registers { identifier value } } }
  }
}
""".strip()

GAS_METER_READINGS = """
query GasReadings($accountNumber: String!, $meterId: String!, $first: Int!, $after: String) {
  gasMeterReadings(accountNumber: $accountNumber, meterId: $meterId, first: $first, after: $after) {
    pageInfo { hasNextPage endCursor }
    edges { node { readAt source readingType registers { identifier value } } }
  }
}
""".strip()

OCTOPLUS = """
query Octoplus($accountNumber: String!) {
  octoplusAccountInfo(accountNumber: $accountNumber) { isOctoplusEnrolled enrollmentStatus }
}
""".strip()
