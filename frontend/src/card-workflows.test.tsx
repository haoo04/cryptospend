// @vitest-environment jsdom

import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Account, Asset, CardRecord, Category } from "./api";
import CardCenter from "./CardCenter";

const assets: Asset[] = [
  {
    id: "myr",
    symbol: "MYR",
    name: "Malaysian Ringgit",
    decimals: 6,
    chain: null,
    contract_address: null,
    active: true,
  },
  {
    id: "usdt",
    symbol: "USDT",
    name: "Tether",
    decimals: 6,
    chain: null,
    contract_address: null,
    active: true,
  },
  {
    id: "usd",
    symbol: "USD",
    name: "US Dollar",
    decimals: 2,
    chain: null,
    contract_address: null,
    active: true,
  },
];

const accounts: Account[] = [
  {
    id: "wallet",
    name: "Wallet",
    account_type: "ASSET",
    channel_type: "CRYPTO_WALLET",
    provider: null,
    closed: false,
    balances: [],
    available_balances: [],
  },
  {
    id: "bank",
    name: "Bank",
    account_type: "ASSET",
    channel_type: "BANK",
    provider: null,
    closed: false,
    balances: [],
    available_balances: [],
  },
  {
    id: "expense",
    name: "General Expense",
    account_type: "EXPENSE",
    channel_type: "OTHER",
    provider: null,
    closed: false,
    balances: [],
    available_balances: [],
  },
  {
    id: "fees",
    name: "Trading Fees",
    account_type: "EXPENSE",
    channel_type: "OTHER",
    provider: null,
    closed: false,
    balances: [],
    available_balances: [],
  },
  {
    id: "income",
    name: "Other Income",
    account_type: "INCOME",
    channel_type: "OTHER",
    provider: null,
    closed: false,
    balances: [],
    available_balances: [],
  },
  {
    id: "gain",
    name: "Realized Gain/Loss",
    account_type: "GAIN_LOSS",
    channel_type: "OTHER",
    provider: null,
    closed: false,
    balances: [],
    available_balances: [],
  },
];

const categories: Category[] = [
  {
    id: "food",
    name: "Food",
    kind: "EXPENSE",
    active: true,
    created_at: "",
    updated_at: "",
  },
  {
    id: "cashback",
    name: "Cashback",
    kind: "INCOME",
    active: true,
    created_at: "",
    updated_at: "",
  },
];

function card(overrides: Partial<CardRecord> = {}): CardRecord {
  return {
    id: "auth-1",
    event_id: null,
    parent_card_transaction_id: null,
    original_transaction_id: null,
    provider: "Bybit",
    provider_account_id: "card-main",
    external_id: "auth-1-external",
    transaction_type: "AUTHORIZATION",
    card_account_id: "wallet",
    merchant_name: "Dinner",
    merchant_country: "MY",
    merchant_amount: "100",
    merchant_asset_id: "myr",
    billing_amount: "23.70",
    billing_asset_id: "usd",
    merchant_value_myr: "100",
    category_id: null,
    expense_account_id: null,
    refunded_value_myr: "0",
    refundable_remaining_myr: null,
    status: "AUTHORIZED",
    authorized_at: "2026-09-20T00:00:00Z",
    settled_at: null,
    hold: {
      account_id: "wallet",
      asset_id: "usdt",
      amount: "23.96",
      value_myr: "101.83",
      status: "ACTIVE",
    },
    rewards: [],
    ...overrides,
  };
}

function renderCenter(
  overrides: Partial<React.ComponentProps<typeof CardCenter>> = {},
) {
  return render(
    <CardCenter
      assets={assets}
      accounts={accounts}
      categories={categories}
      cards={[card()]}
      costs={[]}
      busy={false}
      onAuthorize={vi.fn(async () => true)}
      onReverseAuthorization={vi.fn(async () => true)}
      onSettle={vi.fn(async () => true)}
      onRefund={vi.fn(async () => true)}
      onReward={vi.fn(async () => true)}
      onCreditReward={vi.fn(async () => true)}
      {...overrides}
    />,
  );
}

function openSettlement() {
  fireEvent.click(screen.getByRole("button", { name: "SETTLE" }));
  fireEvent.change(screen.getByLabelText("Authorization"), {
    target: { value: "auth-1" },
  });
  fireEvent.change(screen.getByLabelText("Expense account"), {
    target: { value: "expense" },
  });
  fireEvent.change(screen.getByLabelText("Category"), {
    target: { value: "food" },
  });
  fireEvent.change(screen.getByLabelText("Gain/loss account"), {
    target: { value: "gain" },
  });
  fireEvent.change(screen.getByLabelText("Funding account 1"), {
    target: { value: "wallet" },
  });
  fireEvent.change(screen.getByLabelText("Funding asset 1"), {
    target: { value: "usdt" },
  });
  fireEvent.change(screen.getByLabelText("Funding quantity 1"), {
    target: { value: "23.96" },
  });
  fireEvent.change(screen.getByLabelText("Funding transaction value 1"), {
    target: { value: "100" },
  });
  fireEvent.change(screen.getByLabelText("Funding reference value 1"), {
    target: { value: "101.83" },
  });
}

afterEach(cleanup);

describe("card workflow forms", () => {
  it("autofills linked authorization identity and always submits a final capture", async () => {
    const onSettle = vi.fn(async () => true);
    renderCenter({
      cards: [
        card(),
        card({
          id: "partial",
          external_id: "partial-auth",
          status: "PARTIALLY_SETTLED",
          merchant_name: "Old capture",
        }),
      ],
      onSettle,
    });
    openSettlement();

    expect(screen.queryByRole("option", { name: /Old capture/ })).toBeNull();
    expect(screen.getByLabelText("Provider")).toHaveProperty("value", "Bybit");
    expect(screen.getByLabelText("Provider")).toHaveProperty("readOnly", true);
    expect(screen.getByLabelText("Merchant")).toHaveProperty("value", "Dinner");
    fireEvent.change(screen.getByLabelText("Settlement external ID"), {
      target: { value: "settlement-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Post settlement" }));

    await waitFor(() =>
      expect(onSettle).toHaveBeenCalledWith(
        expect.objectContaining({
          authorization_id: "auth-1",
          final_capture: true,
          funding_legs: [
            expect.objectContaining({ transaction_value_myr: "100" }),
          ],
        }),
      ),
    );
  });

  it("submits multiple funding legs and explicit fees with balanced totals", async () => {
    const onSettle = vi.fn(async () => true);
    renderCenter({ onSettle });
    openSettlement();
    fireEvent.click(screen.getByRole("button", { name: "Add funding leg" }));
    fireEvent.change(screen.getByLabelText("Funding account 2"), {
      target: { value: "bank" },
    });
    fireEvent.change(screen.getByLabelText("Funding asset 2"), {
      target: { value: "usdt" },
    });
    fireEvent.change(screen.getByLabelText("Funding quantity 2"), {
      target: { value: "10" },
    });
    fireEvent.change(screen.getByLabelText("Funding transaction value 2"), {
      target: { value: "40" },
    });
    fireEvent.change(screen.getByLabelText("Funding reference value 2"), {
      target: { value: "40" },
    });
    fireEvent.change(screen.getByLabelText("Funding transaction value 1"), {
      target: { value: "61" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add fee" }));
    fireEvent.change(screen.getByLabelText("Fee asset 1"), {
      target: { value: "usdt" },
    });
    fireEvent.change(screen.getByLabelText("Fee quantity 1"), {
      target: { value: "0.2" },
    });
    fireEvent.change(screen.getByLabelText("Fee value MYR 1"), {
      target: { value: "1" },
    });
    fireEvent.change(screen.getByLabelText("Fee expense account 1"), {
      target: { value: "fees" },
    });
    fireEvent.click(screen.getByLabelText("Included in funding amount"));
    fireEvent.click(screen.getByRole("button", { name: "Post settlement" }));

    await waitFor(() =>
      expect(onSettle).toHaveBeenCalledWith(
        expect.objectContaining({
          funding_legs: expect.arrayContaining([
            expect.objectContaining({ transaction_value_myr: "61" }),
            expect.objectContaining({ transaction_value_myr: "40" }),
          ]),
          fees: [
            expect.objectContaining({
              value_myr: "1",
              included_in_funding_amount: true,
            }),
          ],
        }),
      ),
    );
  });

  it("uses server-owned refund fields and supports multiple returned assets", async () => {
    const onRefund = vi.fn(async () => true);
    renderCenter({
      cards: [
        card({
          id: "purchase-1",
          transaction_type: "PURCHASE",
          status: "PARTIALLY_REFUNDED",
          event_id: "event-1",
          merchant_amount: "100",
          merchant_value_myr: "100",
          expense_account_id: "expense",
          category_id: "food",
          refunded_value_myr: "40",
          refundable_remaining_myr: "60",
          hold: null,
          rewards: [],
        }),
      ],
      onRefund,
    });
    fireEvent.click(screen.getByRole("button", { name: "REFUND" }));
    fireEvent.change(screen.getByLabelText("Purchase"), {
      target: { value: "purchase-1" },
    });
    expect(screen.getByText("General Expense")).toBeTruthy();
    expect(screen.queryByLabelText("Refund value MYR")).toBeNull();
    expect(
      screen.queryByRole("combobox", { name: "Original expense account" }),
    ).toBeNull();
    fireEvent.change(screen.getByLabelText("Receiving account 1"), {
      target: { value: "wallet" },
    });
    fireEvent.change(screen.getByLabelText("Returned asset 1"), {
      target: { value: "usd" },
    });
    fireEvent.change(screen.getByLabelText("Returned quantity 1"), {
      target: { value: "9" },
    });
    fireEvent.change(screen.getByLabelText("Transaction value MYR 1"), {
      target: { value: "40" },
    });
    fireEvent.change(screen.getByLabelText("Reference value MYR 1"), {
      target: { value: "39.95" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add returned asset" }));
    fireEvent.change(screen.getByLabelText("Receiving account 2"), {
      target: { value: "bank" },
    });
    fireEvent.change(screen.getByLabelText("Returned asset 2"), {
      target: { value: "myr" },
    });
    fireEvent.change(screen.getByLabelText("Returned quantity 2"), {
      target: { value: "20" },
    });
    fireEvent.change(screen.getByLabelText("Transaction value MYR 2"), {
      target: { value: "20" },
    });
    fireEvent.change(screen.getByLabelText("Reference value MYR 2"), {
      target: { value: "19.95" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Post refund" }));

    await waitFor(() =>
      expect(onRefund).toHaveBeenCalledWith(
        "purchase-1",
        expect.objectContaining({
          refund_legs: expect.any(Array),
        }),
      ),
    );
    const refundCalls = onRefund.mock.calls as unknown as Array<
      [string, Record<string, unknown>]
    >;
    const payload = refundCalls[0][1];
    expect(payload.refund_legs).toHaveLength(2);
    expect(Object.hasOwn(payload, "refund_value_myr")).toBe(false);
    expect(Object.hasOwn(payload, "expense_account_id")).toBe(false);
    expect(Object.hasOwn(payload, "full_refund")).toBe(false);
  });

  it("previews reward rate and omits the editable rate from the request", async () => {
    const onCreditReward = vi.fn(async () => true);
    renderCenter({
      cards: [
        card({
          id: "purchase-1",
          transaction_type: "PURCHASE",
          status: "SETTLED",
          event_id: "event-1",
          hold: null,
          rewards: [
            {
              id: "reward-1",
              asset_id: "usdt",
              amount: "1",
              status: "PENDING",
              value_myr: null,
            },
          ],
        }),
      ],
      onCreditReward,
    });
    fireEvent.click(screen.getByRole("button", { name: "REWARD" }));
    fireEvent.change(screen.getByLabelText("Pending reward"), {
      target: { value: "reward-1" },
    });
    fireEvent.change(screen.getByLabelText("Income account"), {
      target: { value: "income" },
    });
    fireEvent.change(screen.getByLabelText("Reward category"), {
      target: { value: "cashback" },
    });
    fireEvent.change(screen.getByLabelText("Reward value MYR"), {
      target: { value: "4.25" },
    });
    expect(screen.getByLabelText("Derived rate")).toHaveProperty(
      "value",
      "4.25",
    );
    expect(screen.getByLabelText("Derived rate")).toHaveProperty(
      "readOnly",
      true,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Post credited reward" }),
    );

    await waitFor(() =>
      expect(onCreditReward).toHaveBeenCalledWith(
        "reward-1",
        expect.objectContaining({ value_myr: "4.25" }),
      ),
    );
    const creditCalls = onCreditReward.mock.calls as unknown as Array<
      [string, Record<string, unknown>]
    >;
    expect(Object.hasOwn(creditCalls[0][1], "valuation_rate")).toBe(false);
  });
});
