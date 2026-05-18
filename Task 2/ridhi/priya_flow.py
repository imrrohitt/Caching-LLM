"""
Priya onboarding conversation flow — plain Python state machine.

Why not LangGraph?
- Only 3 deterministic checkpoints + session metadata.
- Easier to unit-test Monday→Thursday simulation without LLM variance.
- LangGraph is better when Priya adds OCR, CRM tools, and human handoff (6+ nodes).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ridhi.checkpoints import Checkpoint, OnboardingData
from ridhi.hindi_prompts import PRIYA_PROMPTS, generate_reengage_hindi
from ridhi.state_manager import CPState, SessionStateManager, _parse_iso, _utcnow
from ridhi.templates import REENGAGE_MID_HI, render_template


@dataclass
class FlowResult:
    replies: list[str]
    state: CPState
    session_was_expired: bool
    used_template: bool
    template_name: str | None = None
    advanced_checkpoint: bool = False


class PriyaFlow:
  def __init__(self, state_manager: SessionStateManager) -> None:
      self._sm = state_manager

  def handle_message(
      self,
      wa_id: str,
      text: str,
      *,
      message_time: datetime | None = None,
      wamid: str | None = None,
  ) -> FlowResult:
      if wamid and not self._sm.claim_message_id(wa_id, wamid):
          state = self._sm.get_or_create(wa_id)
          return FlowResult(replies=[], state=state, session_was_expired=False, used_template=False)

      # Detect 24h expiry BEFORE resetting the session window
      prior = self._sm.load_state(wa_id) or self._sm.get_or_create(wa_id)
      session_expired = self._session_expired_before(prior, message_time)

      state = self._sm.record_user_message(wa_id, at=message_time)

      if session_expired:
          self._sm.mark_re_engagement(wa_id)
          state = self._sm.load_state(wa_id) or state

      replies: list[str] = []
      used_template = False
      template_name: str | None = None
      advanced = False

      if session_expired:
          reengage = generate_reengage_hindi(
              state.data.cp_name or "",
              state.last_checkpoint.value,
          )
          replies.append(reengage)

      checkpoint = state.last_checkpoint
      normalized = text.strip().lower()

      if checkpoint == Checkpoint.NAME_COLLECTION:
          replies.extend(self._handle_name(state, text))
          advanced = state.data.cp_name is not None

      elif checkpoint == Checkpoint.PROJECT_INTEREST:
          replies.extend(self._handle_project(state, text))
          advanced = len(state.data.project_ids) > 0

      elif checkpoint == Checkpoint.EOI_CONFIRMATION:
          replies.extend(self._handle_eoi(state, normalized))
          advanced = state.data.eoi_accepted

      elif checkpoint == Checkpoint.COMPLETED:
          replies.append(
              PRIYA_PROMPTS["completed_hi"].format(name=state.data.cp_name or "साथी")
          )

      state = self._sm.load_state(wa_id) or state
      for _ in replies:
          state = self._sm.record_bot_message(wa_id)

      return FlowResult(
          replies=replies,
          state=state,
          session_was_expired=session_expired,
          used_template=used_template,
          template_name=template_name,
          advanced_checkpoint=advanced,
      )

  @staticmethod
  def _session_expired_before(state: CPState, message_time: datetime | None) -> bool:
      expires = _parse_iso(state.session_window_expires_at)
      if expires is None:
          return False
      at = message_time or _utcnow()
      return at > expires

  def trigger_business_reengagement(self, wa_id: str) -> FlowResult:
      """
      Business-initiated message after 24h window (requires template).
      Used when PropOS nudges a silent CP without inbound message first.
      """
      state = self._sm.load_state(wa_id) or self._sm.get_or_create(wa_id)
      if state.last_checkpoint == Checkpoint.EOI_CONFIRMATION:
          from ridhi.templates import REENGAGE_NEAR_COMPLETE_HI

          template = REENGAGE_NEAR_COMPLETE_HI
      else:
          template = REENGAGE_MID_HI

      body = render_template(template, state.data.cp_name or "साथी")
      self._sm.mark_re_engagement(wa_id)
      return FlowResult(
          replies=[body],
          state=self._sm.load_state(wa_id) or state,
          session_was_expired=True,
          used_template=True,
          template_name=template.name,
      )

  def _handle_name(self, state: CPState, text: str) -> list[str]:
      name = text.strip()
      if len(name) < 2:
          return [PRIYA_PROMPTS["ask_name_hi"]]

      data = state.data
      data.cp_name = name
      nxt = Checkpoint.PROJECT_INTEREST
      self._complete_checkpoint(state, Checkpoint.NAME_COLLECTION, data, nxt)
      return [PRIYA_PROMPTS["ask_project_hi"].format(name=name)]

  def _handle_project(self, state: CPState, text: str) -> list[str]:
      projects = _parse_projects(text)
      if not projects:
          return [
              PRIYA_PROMPTS["ask_project_hi"].format(
                  name=state.data.cp_name or "साथी"
              )
          ]

      data = state.data
      data.project_ids = projects
      nxt = Checkpoint.EOI_CONFIRMATION
      self._complete_checkpoint(state, Checkpoint.PROJECT_INTEREST, data, nxt)
      return [PRIYA_PROMPTS["ask_eoi_hi"].format(name=data.cp_name or "साथी")]

  def _handle_eoi(self, state: CPState, normalized: str) -> list[str]:
      confirm_words = {"हाँ", "हां", "haan", "han", "yes", "y", "पुष्टि", "confirm", "ok"}
      if normalized not in confirm_words and not any(
          w in normalized for w in ("हाँ", "हां", "पुष्टि")
      ):
          return [PRIYA_PROMPTS["ask_eoi_hi"].format(name=state.data.cp_name or "साथी")]

      data = state.data
      data.eoi_accepted = True
      self._complete_checkpoint(state, Checkpoint.EOI_CONFIRMATION, data, Checkpoint.COMPLETED)
      return [PRIYA_PROMPTS["completed_hi"].format(name=data.cp_name or "साथी")]

  def _complete_checkpoint(
      self,
      state: CPState,
      finished: Checkpoint,
      data: OnboardingData,
      nxt: Checkpoint,
  ) -> None:
      if finished.value not in state.completed_checkpoints:
          state.completed_checkpoints.append(finished.value)
      state.last_checkpoint = nxt
      state.data = data
      self._sm.save_state(state)


def _parse_projects(text: str) -> list[str]:
      mapping = {
          "1": "proj_sunrise",
          "sunrise": "proj_sunrise",
          "2": "proj_green",
          "green": "proj_green",
          "valley": "proj_green",
      }
      found: list[str] = []
      lower = text.lower()
      for key, pid in mapping.items():
          if key in lower and pid not in found:
              found.append(pid)
      if not found and len(text.strip()) > 2:
          found.append(f"proj_custom_{text.strip()[:20]}")
      return found
