from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
from faker import Faker

from .ledger import ImmutableLedger
from .policy import PolicyEngine, PolicyVersion
from .reconciliation import ReconciliationEngine, DisputeCenter, ReconciliationFinding
from .external_signals import ExternalSignals, MarketSignal
from .trust import TrustLayer, TrustAlert
from .narratives import BoardNarratives, DecisionMemory
from .plugins import PluginRegistry

fake = Faker()

CAP_TABLE_COLUMNS = ["Holder", "ShareClass", "Shares", "Region", "Department"]
GRANTS_COLUMNS = ["Employee", "GrantType", "ShareClass", "Shares", "StrikePrice", "GrantDate", "VestingMonths", "CliffMonths", "Department", "Region", "Status"]

DEFAULT_SHARE_CLASSES = ["Common", "Preferred", "OptionPool", "Warrant", "RSU", "ISO", "NSO", "EMI"]
DEFAULT_GRANT_TYPES = ["ISO", "NSO", "RSU", "Warrant", "EMI"]

@dataclass
class CompanyState:
    company_id: str
    name: str
    cap_table: pd.DataFrame
    grants: pd.DataFrame
    valuation: Dict
    is_frozen: bool = False
    freeze_reason: str = ""

class FoundryPlatform:
    """Enterprise platform state container (multi-company, role-aware)."""

    def __init__(self) -> None:
        self.ledger = ImmutableLedger()
        self.policy = PolicyEngine()
        self.recon = ReconciliationEngine()
        self.disputes = DisputeCenter()
        self.signals = ExternalSignals()
        self.trust = TrustLayer()
        self.narratives = BoardNarratives()
        self.plugins = PluginRegistry()

        self.companies: Dict[str, CompanyState] = {}
        self.current_company_id: Optional[str] = None

    # ---------- Companies ----------
    def add_company(self, name: str, company_id: Optional[str] = None) -> str:
        company_id = company_id or fake.uuid4().replace("-", "")
        cap = pd.DataFrame(columns=CAP_TABLE_COLUMNS)
        grants = pd.DataFrame(columns=GRANTS_COLUMNS)
        self.companies[company_id] = CompanyState(company_id, name, cap, grants, valuation={})
        if self.current_company_id is None:
            self.current_company_id = company_id
        self.ledger.append(company_id=company_id, entity_id=company_id, event_type="CAPTABLE_UPSERT",
                           actor="system", role="admin", payload={"action":"company_created","name":name})
        return company_id

    def switch_company(self, company_id: str) -> None:
        if company_id not in self.companies:
            raise ValueError("Unknown company_id")
        self.current_company_id = company_id

    @property
    def company(self) -> CompanyState:
        if not self.current_company_id or self.current_company_id not in self.companies:
            raise ValueError("No company selected")
        return self.companies[self.current_company_id]

    # ---------- Demo data ----------
    def ensure_demo(self) -> None:
        if not self.companies:
            demo_id = self.add_company("Demo Company", company_id="demo")
            self._load_demo_data(demo_id)

    def _load_demo_data(self, company_id: str) -> None:
        cap = pd.DataFrame([
            {"Holder":"Founders", "ShareClass":"Common", "Shares": 6_000_000, "Region":"US", "Department":"Founders"},
            {"Holder":"Seed Investors", "ShareClass":"Preferred", "Shares": 2_000_000, "Region":"US", "Department":"Investors"},
            {"Holder":"Option Pool", "ShareClass":"OptionPool", "Shares": 2_000_000, "Region":"US", "Department":"HR"},
        ], columns=CAP_TABLE_COLUMNS)

        grants = pd.DataFrame([
            {"Employee":"A. Patel", "GrantType":"ISO", "ShareClass":"ISO", "Shares": 50_000, "StrikePrice": 1.25,
             "GrantDate":"2025-01-15", "VestingMonths": 48, "CliffMonths": 12, "Department":"Engineering", "Region":"US", "Status":"Issued"},
            {"Employee":"M. Chen", "GrantType":"RSU", "ShareClass":"RSU", "Shares": 20_000, "StrikePrice": 0.00,
             "GrantDate":"2025-03-01", "VestingMonths": 48, "CliffMonths": 12, "Department":"Product", "Region":"US", "Status":"Issued"},
        ], columns=GRANTS_COLUMNS)

        self.companies[company_id].cap_table = cap
        self.companies[company_id].grants = grants

    # ---------- Freeze / Close lock ----------
    def freeze(self, reason: str, actor: str="finance") -> None:
        c = self.company
        c.is_frozen = True
        c.freeze_reason = reason
        self.ledger.append(company_id=c.company_id, entity_id=c.company_id, event_type="CLOSE_FREEZE", actor=actor, role="cfo",
                           payload={"reason":reason})

    def unfreeze(self, actor: str="finance") -> None:
        c = self.company
        c.is_frozen = False
        c.freeze_reason = ""
        self.ledger.append(company_id=c.company_id, entity_id=c.company_id, event_type="CLOSE_FREEZE", actor=actor, role="cfo",
                           payload={"reason":"unfreeze"})

    # ---------- Upserts with governance ----------
    def set_cap_table(self, df: pd.DataFrame, actor: str="admin") -> None:
        c = self.company
        if c.is_frozen:
            raise PermissionError(f"Company is frozen: {c.freeze_reason}")
        df = df.copy()
        df = self._normalize_cap(df)
        c.cap_table = df
        self.ledger.append(company_id=c.company_id, entity_id=c.company_id, event_type="CAPTABLE_UPSERT", actor=actor, role="admin",
                           payload={"rows": len(df)})

    def set_grants(self, df: pd.DataFrame, actor: str="admin") -> None:
        c = self.company
        if c.is_frozen:
            raise PermissionError(f"Company is frozen: {c.freeze_reason}")
        df = df.copy()
        df = self._normalize_grants(df)
        c.grants = df
        self.ledger.append(company_id=c.company_id, entity_id=c.company_id, event_type="GRANT_ISSUED", actor=actor, role="hr",
                           payload={"rows": len(df)})

    def _normalize_cap(self, df: pd.DataFrame) -> pd.DataFrame:
        for col in CAP_TABLE_COLUMNS:
            if col not in df.columns:
                df[col] = "" if col != "Shares" else 0
        df["Shares"] = pd.to_numeric(df["Shares"], errors="coerce").fillna(0.0)
        df["ShareClass"] = df["ShareClass"].astype(str).str.strip()
        df.loc[~df["ShareClass"].isin(DEFAULT_SHARE_CLASSES), "ShareClass"] = "Common"
        return df[CAP_TABLE_COLUMNS]

    def _normalize_grants(self, df: pd.DataFrame) -> pd.DataFrame:
        for col in GRANTS_COLUMNS:
            if col not in df.columns:
                df[col] = "" if col not in ("Shares","StrikePrice","VestingMonths","CliffMonths") else 0
        df["Shares"] = pd.to_numeric(df["Shares"], errors="coerce").fillna(0.0)
        df["StrikePrice"] = pd.to_numeric(df["StrikePrice"], errors="coerce").fillna(0.0)
        df["VestingMonths"] = pd.to_numeric(df["VestingMonths"], errors="coerce").fillna(48).astype(int)
        df["CliffMonths"] = pd.to_numeric(df["CliffMonths"], errors="coerce").fillna(12).astype(int)
        df["GrantType"] = df["GrantType"].astype(str).str.strip()
        df.loc[~df["GrantType"].isin(DEFAULT_GRANT_TYPES), "GrantType"] = "NSO"
        df["ShareClass"] = df["ShareClass"].astype(str).str.strip()
        df.loc[~df["ShareClass"].isin(DEFAULT_SHARE_CLASSES), "ShareClass"] = df["GrantType"]
        df["Status"] = df["Status"].replace("", "Issued")
        return df[GRANTS_COLUMNS]

    # ---------- Reporting ----------
    def cap_summary(self) -> pd.DataFrame:
        df = self.company.cap_table.copy()
        if df.empty:
            return pd.DataFrame(columns=["ShareClass", "Shares"])
        df["Shares"] = pd.to_numeric(df["Shares"], errors="coerce").fillna(0.0)
        return df.groupby("ShareClass", as_index=False)["Shares"].sum().sort_values("Shares", ascending=False)

    def total_shares(self) -> float:
        df = self.company.cap_table
        if df.empty: return 0.0
        return float(pd.to_numeric(df["Shares"], errors="coerce").fillna(0.0).sum())

    # ---------- Waterfall (simple) ----------
    def simple_waterfall(self, exit_value: float) -> pd.DataFrame:
        df = self.company.cap_table.copy()
        if df.empty:
            return pd.DataFrame(columns=["Holder","ShareClass","Shares","Payout"])
        df["Shares"] = pd.to_numeric(df["Shares"], errors="coerce").fillna(0.0)
        total = df["Shares"].sum()
        if total <= 0:
            df["Payout"] = 0.0
        else:
            df["Payout"] = df["Shares"] / total * float(exit_value)
        return df[["Holder","ShareClass","Shares","Payout"]].sort_values("Payout", ascending=False)

    # ---------- Recon ----------
    def run_reconciliation(self, external_cap: pd.DataFrame, system_name: str) -> List[ReconciliationFinding]:
        c = self.company
        findings = self.recon.run_cap_table_recon(c.cap_table, external_cap, system_name=system_name)
        self.ledger.append(company_id=c.company_id, entity_id=c.company_id, event_type="RECONCILIATION_RUN", actor="system", role="cfo",
                           payload={"system": system_name, "findings": len(findings)})
        return findings

    # ---------- Policy ----------
    def apply_policy_to_grants(self, policy: PolicyVersion) -> pd.DataFrame:
        g = self.company.grants.copy()
        if g.empty:
            return pd.DataFrame(columns=["severity","message","employee","shares"])
        violations=[]
        for idx, row in g.iterrows():
            v = self.policy.evaluate(policy, row.to_dict(), "grant", str(idx))
            for vv in v:
                violations.append({"severity": vv.severity, "message": vv.message, "employee": row.get("Employee",""), "shares": row.get("Shares",0)})
        return pd.DataFrame(violations)

    # ---------- External signals ----------
    def get_signals(self, stage: str, industry: str):
        return self.signals.fetch_demo_signals(stage=stage, industry=industry)

    # ---------- Trust ----------
    def trust_report(self) -> Dict[str, float]:
        g = self.company.grants
        fairness = self.trust.perceived_fairness_index(g, group_field="Department") if not g.empty else 0.5
        comprehension = 0.55  # placeholder until quiz table is added
        return {"comprehension": comprehension, "fairness": fairness}

    def trust_alerts(self) -> List[TrustAlert]:
        r = self.trust_report()
        return self.trust.trust_decay_alerts(r["comprehension"], r["fairness"])
