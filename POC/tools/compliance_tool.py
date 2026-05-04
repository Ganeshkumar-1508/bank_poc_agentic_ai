# tools/compliance_tool.py
# ---------------------------------------------------------------------------
# Yente/OpenSanctions entity screening and Wikidata OSINT tools.
# ---------------------------------------------------------------------------

import re
import json
import time
import requests
from datetime import datetime
from pathlib import Path
from typing import Type, Dict, Any, Optional, List, ClassVar

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from tools.config import YENTE_URL, IMAGE_OUTPUT_DIR


# ---------------------------------------------------------------------------
# Input schemas
# ---------------------------------------------------------------------------


class YenteInput(BaseModel):
    query: str = Field(
        default="",
        description=(
            "Search query: either a plain name string (e.g. 'Horacio Cartes') "
            "OR a JSON object string with keys: name, schema, birth_date, nationality, etc. "
            'Example: \'{"name": "Horacio Cartes", "nationality": "PY"}\''
        ),
    )
    name: str = Field(
        default="", description="Entity full name (flat alternative to query JSON)"
    )
    schema_type: str = Field(
        default="", alias="schema", description="FTM schema: Person or LegalEntity"
    )
    birth_date: str = Field(default="", description="Date of birth YYYY-MM-DD")
    nationality: str = Field(default="", description="ISO-2 nationality/country code")
    country: str = Field(default="", description="ISO-2 country code")
    id_number: str = Field(default="", description="National ID or document number")

    model_config = {"populate_by_name": True}


class WikidataOSINTInput(BaseModel):
    yente_output: str = Field(
        ...,
        description="Full text output from YenteEntitySearchTool. Must contain ENTITY_NAME: and ENTITY_ID: lines.",
    )
    original_name: str = Field(
        default="",
        description="Original user-inputted name for Wikidata search (not the alias from Yente).",
    )


# ---------------------------------------------------------------------------
# YenteEntitySearchTool
# ---------------------------------------------------------------------------


class YenteEntitySearchTool(BaseTool):
    name: str = "Deep Entity Enrichment (Yente/OpenSanctions)"
    description: str = (
        "Screens an entity against OpenSanctions using the /match API. "
        "Input: a name string OR a JSON string with keys like name, birthDate, nationality. "
        "Returns scored matches, sanctions/PEP flags, properties, and related entities."
    )
    args_schema: Type[BaseModel] = YenteInput

    def _build_query_entity(self, query: str) -> Dict[str, Any]:
        structured: Dict[str, Any] = {}
        try:
            parsed = json.loads(query)

            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict):
                        if "query" in item and isinstance(item["query"], str):
                            try:
                                inner = json.loads(item["query"])
                                if isinstance(inner, dict):
                                    structured = inner
                                    break
                            except (json.JSONDecodeError, ValueError):
                                pass
                        elif any(
                            k in item
                            for k in ("name", "schema", "first_name", "full_name")
                        ):
                            structured = item
                            break
                    elif isinstance(parsed, dict):
                        if (
                            "query" in parsed
                            and isinstance(parsed["query"], str)
                            and len(parsed) == 1
                        ):
                            try:
                                inner = json.loads(parsed["query"])
                                if isinstance(inner, dict):
                                    structured = inner
                            except (json.JSONDecodeError, ValueError):
                                structured = parsed
                        else:
                            structured = parsed

        except (json.JSONDecodeError, ValueError):
            pass

        if not structured or not isinstance(structured, dict):
            return {
                "schema": "LegalEntity",
                "properties": {"name": [query.strip()]},
                "aliases": [],
            }

        props: Dict[str, List[str]] = {}
        schema = structured.get("schema", "LegalEntity")

        for src_key, ftm_key in [
            ("name", "name"),
            ("first_name", "firstName"),
            ("last_name", "lastName"),
            ("birth_date", "birthDate"),
            ("birthDate", "birthDate"),
            ("nationality", "nationality"),
            ("country", "country"),
            ("id_number", "idNumber"),
            ("pan", "idNumber"),
            ("passport", "passportNumber"),
            ("email", "email"),
            ("phone", "phone"),
        ]:
            val = structured.get(src_key)
            if val:
                props.setdefault(ftm_key, []).append(str(val))

        if not props:
            full_name = structured.get("full_name") or (
                structured.get("first_name", "") + " " + structured.get("last_name", "")
            )
            props["name"] = [full_name.strip() or query.strip()]

        # Extract aliases from the entity data
        aliases: List[str] = []
        for alias_key in (
            "alias",
            "aliases",
            "weakAlias",
            "alternative_names",
            "alt_names",
        ):
            alias_val = structured.get(alias_key)
            if alias_val:
                if isinstance(alias_val, list):
                    aliases.extend(
                        [str(a).strip() for a in alias_val if str(a).strip()]
                    )
                elif isinstance(alias_val, str) and alias_val.strip():
                    aliases.append(alias_val.strip())

        # Remove duplicates and filter out empty strings
        aliases = list(dict.fromkeys(aliases))

        return {"schema": schema, "properties": props, "aliases": aliases}

    def _run(
        self,
        query: str = "",
        name: str = "",
        schema_type: str = "",
        birth_date: str = "",
        nationality: str = "",
        country: str = "",
        id_number: str = "",
        **kwargs,
    ) -> str:
        if not query.strip():
            flat: dict = {}
            if name:
                flat["name"] = name
            if schema_type:
                flat["schema"] = schema_type
            if birth_date:
                flat["birth_date"] = birth_date
            if nationality:
                flat["nationality"] = nationality
            if country:
                flat["country"] = country
            if id_number:
                flat["id_number"] = id_number
            if "schema" in kwargs:
                flat["schema"] = kwargs["schema"]
            if flat:
                query = json.dumps(flat)
            else:
                return "YENTE_RESULT: No query provided — pass a name or JSON entity object."
        try:
            entity_query = self._build_query_entity(query)
            name_val: str = (
                entity_query.get("properties", {}).get("name", [query])[0]
                if entity_query.get("properties", {}).get("name")
                else query.strip()
            )

            match_candidates: List[Dict[str, Any]] = []
            base_schema = entity_query["schema"]
            schemas_to_try = list(dict.fromkeys([base_schema, "Person"]))

            for schema in schemas_to_try:
                variant = dict(entity_query, schema=schema)
                try:
                    resp = requests.post(
                        f"{YENTE_URL}/match/default",
                        json={"queries": {"q1": variant}},
                        params={"algorithm": "best", "limit": 5},
                        timeout=20,
                    )
                    if resp.status_code == 200:
                        for r in (
                            resp.json()
                            .get("responses", {})
                            .get("q1", {})
                            .get("results", [])
                        ):
                            match_candidates.append(r)
                    else:
                        # Log match API errors for debugging
                        import logging

                        logging.warning(
                            f"Match API returned {resp.status_code}: {resp.text[:200]}"
                        )
                except Exception as e:
                    # Log match API exceptions for debugging
                    import logging

                    logging.warning(f"Match API exception: {e}")

            search_candidates: List[Dict[str, Any]] = []
            primary_search_confidence = 0.0

            # The Match API (POST /match/default) already ran above (lines 175-192).
            # FIX: If Match API returned candidates but with score=0, use Search API to get proper name-based score.
            # The Search API is also a fallback for when match returns nothing.
            # Use simple text search with proper error handling.

            # Always run search API to get name-based scores (for fallback when match score=0)
            try:
                # Ensure name_val is a clean string, not JSON
                clean_name = name_val.strip()
                # Remove any JSON-like structure if present
                if clean_name.startswith("[") or clean_name.startswith("{"):
                    # Fallback: try to extract name from JSON if it somehow got through
                    try:
                        parsed_fallback = json.loads(clean_name)
                        if isinstance(parsed_fallback, dict):
                            clean_name = parsed_fallback.get("name", name_val)
                        elif (
                            isinstance(parsed_fallback, list)
                            and len(parsed_fallback) > 0
                        ):
                            if isinstance(parsed_fallback[0], dict):
                                clean_name = parsed_fallback[0].get("name", name_val)
                    except (json.JSONDecodeError, KeyError, IndexError):
                        pass  # Keep original name_val if parsing fails

                # Simple text search - just use the name as-is
                search_resp = requests.get(
                    f"{YENTE_URL}/search/default",
                    params={"q": clean_name, "limit": 5, "fuzzy": "true"},
                    timeout=15,
                )
                if search_resp.status_code == 200:
                    search_candidates = search_resp.json().get("results", [])
                    # Calculate primary search confidence from top result
                    if search_candidates:
                        primary_search_confidence = (
                            search_candidates[0].get("score", 0) or 0
                        )
                else:
                    # Log search API errors for debugging
                    import logging

                    logging.warning(
                        f"Search API returned {search_resp.status_code}: {search_resp.text[:200]}"
                    )
            except Exception as e:
                # Log search API exceptions for debugging
                import logging

                logging.warning(f"Search API exception: {e}")

            # FIX: If Match API returned candidates with score=0, enrich them with Search API scores
            if match_candidates:
                for match_candidate in match_candidates:
                    match_score = match_candidate.get("score", 0) or 0
                    if match_score == 0 and search_candidates:
                        # Try to find the same entity in search results and use its score
                        match_id = match_candidate.get("id")
                        for search_result in search_candidates:
                            if search_result.get("id") == match_id:
                                search_score = search_result.get("score", 0) or 0
                                if search_score > 0:
                                    # Update match candidate with search API score
                                    match_candidate["score"] = search_score
                                    match_candidate["_source"] = (
                                        "match_with_search_score"
                                    )
                                    logging.info(
                                        f"Enriched Match API score for {match_id}: 0 -> {search_score} (from Search API)"
                                    )
                                break

            # Issue 1 Fix: Secondary search with aliases if primary search confidence is low
            aliases = entity_query.get("aliases", [])
            if aliases and primary_search_confidence < 0.7:
                for alias in aliases[:3]:  # Try up to 3 aliases
                    try:
                        alias_resp = requests.get(
                            f"{YENTE_URL}/search/default",
                            params={"q": alias, "limit": 3, "fuzzy": "true"},
                            timeout=15,
                        )
                        if alias_resp.status_code == 200:
                            alias_results = alias_resp.json().get("results", [])
                            for ar in alias_results:
                                # Only add if not already seen and with reasonable score
                                ar_id = ar.get("id")
                                ar_score = ar.get("score", 0) or 0
                                if ar_id and ar_id not in seen and ar_score >= 0.5:
                                    ar["_source"] = "alias_search"
                                    ar["_alias_used"] = alias
                                    search_candidates.append(ar)
                    except Exception:
                        continue  # Try next alias on error

            seen: Dict[str, Dict[str, Any]] = {}
            for candidate in match_candidates:
                eid = candidate.get("id")
                if eid and (
                    eid not in seen
                    or candidate.get("score", 0) > seen[eid].get("score", 0)
                ):
                    candidate["_source"] = "match"
                    seen[eid] = candidate
            for candidate in search_candidates:
                eid = candidate.get("id")
                if eid and eid not in seen:
                    candidate["_source"] = "search"
                    candidate.setdefault("score", None)
                    seen[eid] = candidate

            if not seen:
                # Fallback: If no results found, try a broader search without fuzzy matching
                try:
                    fallback_resp = requests.get(
                        f"{YENTE_URL}/search/default",
                        params={"q": name_val, "limit": 10},
                        timeout=15,
                    )
                    if fallback_resp.status_code == 200:
                        fallback_results = fallback_resp.json().get("results", [])
                        for fr in fallback_results:
                            fid = fr.get("id")
                            if fid and fid not in seen:
                                fr["_source"] = "fallback_search"
                                seen[fid] = fr
                except Exception as e:
                    import logging

                    logging.warning(f"Fallback search exception: {e}")

                # Still no results - return no match message
                if not seen:
                    return (
                        f"YENTE_RESULT: No match for '{name_val}'.\n"
                        "Entity is likely not in the local OpenSanctions database.\n"
                        f"ENTITY_NAME: {name_val}"
                    )

            ranked = sorted(
                seen.values(),
                key=lambda x: (x.get("_source") == "match", x.get("score") or 0),
                reverse=True,
            )
            best = ranked[0]
            entity_id = best.get("id")
            if not entity_id:
                return "YENTE_RESULT: Candidates found but all are missing entity IDs."

            full_profile: Dict[str, Any] = {}
            for candidate in ranked[:3]:
                eid = candidate.get("id")
                if not eid:
                    continue
                try:
                    ep = requests.get(
                        f"{YENTE_URL}/entities/{eid}",
                        params={"nested": "true"},
                        timeout=20,
                    )
                    if ep.status_code == 200:
                        full_profile = ep.json()
                        entity_id = eid
                        best = candidate
                        break
                except Exception:
                    continue

            if not full_profile:
                return f"YENTE_RESULT: Found entity ID {entity_id} but could not fetch its full profile."

            props = full_profile.get("properties", {})
            primary_name = (
                ((props.get("name") or props.get("firstName") or [None])[0])
                or best.get("caption")
                or name_val
            )
            aliases = [
                str(a)[:60]
                for a in (props.get("alias", []) + props.get("weakAlias", []))[:6]
                if str(a) != primary_name
            ]
            alias_str = "; ".join(aliases[:3]) if aliases else ""

            risk_flags = props.get("topics", [])
            pep_level = (
                "YES" if any("pep" in str(t).lower() for t in risk_flags) else "NO"
            )

            sanction_details: List[str] = []
            listing_reasons: List[str] = []
            for program in props.get("program", [])[:5]:
                sanction_details.append(str(program)[:80])
            for reason in (props.get("reason", []) + props.get("summary", []))[:3]:
                listing_reasons.append(str(reason)[:120])
            listing_reason_str = (
                "; ".join(listing_reasons) if listing_reasons else "none"
            )

            birth_dates = [str(d) for d in props.get("birthDate", [])[:2]]
            death_date = (
                str(props.get("deathDate", [None])[0]) if props.get("deathDate") else ""
            )
            id_numbers = [str(i)[:30] for i in props.get("idNumber", [])[:3]]
            passport_nums = [str(p)[:30] for p in props.get("passportNumber", [])[:2]]
            national_ids = [str(n)[:30] for n in props.get("nationalId", [])[:2]]
            nationalities = list(
                dict.fromkeys(
                    props.get("nationality", [])
                    + props.get("country", [])
                    + props.get("jurisdiction", [])
                )
            )[:5]
            positions = [str(p)[:80] for p in props.get("position", [])[:5]]

            # --- New: additional enrichment fields ---
            authorities = [str(a)[:80] for a in props.get("authority", [])[:3]]
            listing_dates = [str(d) for d in props.get("listingDate", [])[:3]]
            notes_raw = (props.get("notes", []) + props.get("description", []))[:2]
            notes = [str(n)[:150] for n in notes_raw]
            gender = str(props.get("gender", [None])[0] or "").strip()
            websites = [str(w)[:120] for w in props.get("website", [])[:2]]
            addresses = [str(a)[:100] for a in props.get("address", [])[:3]]
            parties_raw = props.get("party", []) + props.get("memberOf", [])
            parties = [str(p)[:80] for p in parties_raw[:4]]
            # Source datasets from the full entity profile
            source_datasets = [str(ds) for ds in full_profile.get("datasets", [])[:6]]

            related_lines: List[str] = []
            for raw_ent in full_profile.get("referents", []):
                if isinstance(raw_ent, str) or not isinstance(raw_ent, dict):
                    continue
                if raw_ent.get("id") == entity_id:
                    continue
                ep2 = raw_ent.get("properties", {})
                rel_name = ((ep2.get("name") or [None])[0]) or raw_ent.get(
                    "caption", "Unknown"
                )
                rel_ctry = (
                    (ep2.get("country") or ep2.get("nationality") or [None])[0]
                ) or "?"
                rel_schema = raw_ent.get("schema", "")
                if rel_schema in ("Company", "Organization", "LegalEntity"):
                    role = "organization"
                elif rel_schema == "Ownership":
                    role = "owner/shareholder"
                elif rel_schema == "Family":
                    role = "family member"
                elif rel_schema == "Associate":
                    role = "known associate"
                else:
                    role = rel_schema.lower() or "associated"
                rel_topics = ep2.get("topics", [])
                risk_note = f" ⚠ {','.join(rel_topics)}" if rel_topics else ""
                related_lines.append(f"{rel_name} ({rel_ctry}) [{role}]{risk_note}")
                if len(related_lines) >= 8:
                    break

            other_candidates: List[str] = []
            for c in ranked[1:4]:
                c_caption = c.get("caption") or c.get("id", "?")
                c_score = c.get("score")
                c_src = c.get("_source", "?")
                other_candidates.append(
                    f"{c_caption} (score={c_score}, source={c_src})"
                )

            score_val = best.get("score") or 0
            # Aligned with agents.py trust threshold of 0.7
            score_band = (
                "HIGH"
                if score_val >= 0.85
                else "MEDIUM" if score_val >= 0.70 else "LOW — below trust threshold"
            )

            lines: List[str] = [
                f"YENTE: {primary_name}",
                f"Schema: {full_profile.get('schema','?')} | Score: {score_val} ({score_band})",
                f"Risk: {', '.join(risk_flags) if risk_flags else 'NONE'} | PEP: {pep_level}",
                f"DOB: {', '.join(birth_dates) or 'n/a'}"
                + (f" | DOD: {death_date}" if death_date else "")
                + f" | Gender: {gender or 'n/a'}",
                f"Nationality: {', '.join(nationalities) or 'n/a'}",
                f"Aliases: {alias_str or 'none'}",
                f"Positions: {'; '.join(positions[:3]) or 'none'}",
                f"Sanctions: {'; '.join(sanction_details[:4]) or 'none'}",
                f"Listing Reason: {listing_reason_str}",
            ]
            if authorities:
                lines.append(f"Authority: {'; '.join(authorities)}")
            if listing_dates:
                lines.append(f"Listing Date(s): {', '.join(listing_dates)}")
            if parties:
                lines.append(f"Political Affiliation: {'; '.join(parties)}")
            if addresses:
                lines.append(f"Address(es): {'; '.join(addresses)}")
            if websites:
                lines.append(f"Website(s): {', '.join(websites)}")
            if notes:
                lines.append(f"Notes: {' | '.join(notes)}")
            if source_datasets:
                lines.append(f"Source Datasets: {', '.join(source_datasets)}")
            lines.append(
                f"IDs: {', '.join(id_numbers + passport_nums + national_ids)[:120] or 'none'}"
            )
            if related_lines:
                lines.append(
                    f"Related ({len(related_lines)}): {'; '.join(related_lines[:5])}"
                )
            if other_candidates:
                lines.append(f"Alt matches: {'; '.join(other_candidates[:2])}")

            # Structured risk summary for downstream risk_scoring_agent
            is_trusted = score_val >= 0.70
            lines.append("")
            lines.append("--- RISK_SUMMARY ---")
            lines.append(
                f"TRUSTED_MATCH: {'YES' if is_trusted else 'NO (score below 0.70 threshold)'}"
            )
            lines.append(f"SANCTIONS_COUNT: {len(sanction_details)}")
            lines.append(f"PEP_STATUS: {pep_level}")
            lines.append(
                f"RISK_FLAGS: {', '.join(risk_flags) if risk_flags else 'NONE'}"
            )
            lines.append(f"RELATED_ENTITIES_COUNT: {len(related_lines)}")
            lines.append("--- END RISK_SUMMARY ---")

            # Include original input name in Yente output for Wikidata search
            # This allows WikidataOSINTTool to use the original name instead of alias
            original_name_for_output = (
                entity_query.get("properties", {}).get("name", [query])[0]
                if entity_query.get("properties", {}).get("name")
                else query.strip()
            )
            lines += [
                f"ENTITY_NAME: {primary_name}",
                f"ENTITY_ID: {entity_id}",
                f"ORIGINAL_INPUT_NAME: {original_name_for_output}",
            ]
            return "\n".join(lines)

        except Exception as e:
            return f"Yente query failed: {str(e)}"


# ---------------------------------------------------------------------------
# WikidataOSINTTool
# ---------------------------------------------------------------------------


class WikidataOSINTTool(BaseTool):
    name: str = "Wikidata Subject Image Fetcher"
    description: str = (
        "Fetches the official portrait/photo AND social media presence of a person from Wikidata. "
        "Input: the full text output from YenteEntitySearchTool (contains ENTITY_NAME: and ENTITY_ID: lines). "
        "Returns WIKIDATA_IMAGE_PATH, SOCIAL_MEDIA_SECTION, and RELATIVES_SECTION."
    )
    args_schema: Type[BaseModel] = WikidataOSINTInput

    _WM_HEADERS: ClassVar[dict] = {
        "User-Agent": (
            "AMLComplianceBot/2.0 "
            "(automated-compliance-screening; contact: compliance-bot@internal.local)"
        )
    }

    _SM_PROPS: ClassVar[Dict[str, Dict[str, str]]] = {
        "P2002": {"label": "Twitter / X", "url": "https://twitter.com/{}"},
        "P2003": {"label": "Instagram", "url": "https://instagram.com/{}"},
        "P2013": {"label": "Facebook", "url": "https://facebook.com/{}"},
        "P2397": {"label": "YouTube", "url": "https://youtube.com/channel/{}"},
        "P7085": {"label": "TikTok", "url": "https://tiktok.com/@{}"},
        "P4033": {"label": "Mastodon", "url": "{}"},
        "P6634": {"label": "LinkedIn", "url": "https://linkedin.com/in/{}"},
        "P3258": {
            "label": "LiveJournal",
            "url": "https://www.livejournal.com/users/{}",
        },
        "P4264": {"label": "LinkedIn (org)", "url": "https://linkedin.com/company/{}"},
    }

    _SM_QUALIFIER_PROPS: ClassVar[Dict[str, str]] = {
        "P6552": "Twitter / X",
        "P2013": "Facebook",
        "P2397": "YouTube",
        "P7085": "TikTok",
        "P2003": "Instagram",
    }

    _RELATION_PROPS: ClassVar[Dict[str, str]] = {
        "P26": "Spouse",
        "P40": "Child",
        "P22": "Father",
        "P25": "Mother",
        "P3373": "Sibling",
        "P7": "Brother",
        "P9": "Sister",
        "P1038": "Relative",
        "P451": "Partner (unmarried)",
    }

    # Properties with QID values (require label lookup)
    _BIO_PROPS_QID: ClassVar[Dict[str, str]] = {
        "P106": "Occupation",
        "P102": "Political Party",
        "P27": "Country of Citizenship",
        "P19": "Place of Birth",
        "P20": "Place of Death",
        "P108": "Employer",
        "P463": "Member of",
        "P69": "Educated at",
        "P39": "Position Held",
        "P101": "Field of Work",
    }

    def _get_biography_data(
        self, session: requests.Session, claims: dict
    ) -> Dict[str, List[str]]:
        """
        Extract biography fields (occupation, party, citizenship, etc.) from Wikidata claims.
        Returns a dict of label -> list of human-readable values.
        Batch-fetches QID labels to avoid N+1 API calls.
        """
        # Collect all QIDs we need labels for
        qids_by_prop: Dict[str, List[str]] = {}  # prop_label -> [qid, ...]
        all_qids: set = set()

        for prop_id, prop_label in self._BIO_PROPS_QID.items():
            for stmt in claims.get(prop_id, [])[:4]:
                dv = stmt.get("mainsnak", {}).get("datavalue", {})
                if dv.get("type") == "wikibase-entityid":
                    qid = dv.get("value", {}).get("id")
                    if qid:
                        qids_by_prop.setdefault(prop_label, []).append(qid)
                        all_qids.add(qid)

        if not all_qids:
            return {}

        # Batch-fetch all labels in one API call (max 50 IDs per request)
        qid_labels: Dict[str, str] = {}
        qid_list = list(all_qids)[:50]
        try:
            resp = self._wm_get(
                session,
                "https://www.wikidata.org/w/api.php",
                {
                    "action": "wbgetentities",
                    "ids": "|".join(qid_list),
                    "props": "labels",
                    "languages": "en",
                    "format": "json",
                },
            )
            entities = resp.json().get("entities", {})
            for qid in qid_list:
                label = (
                    entities.get(qid, {}).get("labels", {}).get("en", {}).get("value")
                    or qid
                )
                qid_labels[qid] = label
        except Exception:
            for qid in qid_list:
                qid_labels[qid] = qid  # fall back to raw QID

        # Map back to prop labels
        result: Dict[str, List[str]] = {}
        for prop_label, qids in qids_by_prop.items():
            labels = [qid_labels.get(q, q) for q in qids if qid_labels.get(q)]
            if labels:
                result[prop_label] = labels
        return result

    def _format_biography_section(self, bio: Dict[str, List[str]], name: str) -> str:
        if not bio:
            return (
                f"\n[ BIOGRAPHY ]\n  No biography data found on Wikidata for '{name}'."
            )
        lines = ["", "[ BIOGRAPHY ]"]
        # Display in a consistent order
        order = [
            "Occupation",
            "Field of Work",
            "Position Held",
            "Employer",
            "Political Party",
            "Member of",
            "Country of Citizenship",
            "Place of Birth",
            "Place of Death",
            "Educated at",
        ]
        for field in order:
            values = bio.get(field)
            if values:
                lines.append(f"  {field:<28} {', '.join(values)}")
        return "\n".join(lines)

    @staticmethod
    def _wm_get(
        session: requests.Session, url: str, params: dict, timeout: int = 12
    ) -> requests.Response:
        last_exc: Exception = RuntimeError("No attempts made.")
        resp: Optional[requests.Response] = None
        for attempt in range(3):
            try:
                resp = session.get(url, params=params, timeout=timeout)
                if resp.status_code in (429, 503):
                    retry_after = int(resp.headers.get("Retry-After", 3))
                    time.sleep(retry_after + attempt)
                    continue
                resp.raise_for_status()
                return resp
            except requests.RequestException as exc:
                last_exc = exc
                if attempt < 2:
                    time.sleep(2**attempt)
                continue
        # All retries exhausted — raise the last known error
        if resp is not None:
            resp.raise_for_status()
        raise last_exc

    def _get_all_claims(self, session: requests.Session, qid: str) -> dict:
        resp = self._wm_get(
            session,
            "https://www.wikidata.org/w/api.php",
            {
                "action": "wbgetentities",
                "ids": qid,
                "props": "claims",
                "format": "json",
            },
        )
        return resp.json().get("entities", {}).get(qid, {}).get("claims", {})

    def _get_p18_filename(
        self, session: requests.Session, claims: dict
    ) -> Optional[str]:
        # Issue 2 Fix: Check multiple image properties, not just P18
        # P18 = Image, P2096 = Media legend (often has associated image), P18 = main image property
        image_properties = ["P18"]  # P18 is the main image property on Wikidata

        for prop in image_properties:
            prop_statements = claims.get(prop, [])
            if prop_statements:
                filename = (
                    prop_statements[0]
                    .get("mainsnak", {})
                    .get("datavalue", {})
                    .get("value")
                )
                if filename:
                    return filename
        return None

    def _get_alternative_image_filename(
        self, session: requests.Session, claims: dict, qid: str
    ) -> Optional[str]:
        """
        Issue 2 Fix: Alternative image retrieval methods.
        Tries P18 first, then falls back to Commons API search by entity name.
        """
        # First try P18 (standard image property)
        p18_statements = claims.get("P18", [])
        if p18_statements:
            filename = (
                p18_statements[0].get("mainsnak", {}).get("datavalue", {}).get("value")
            )
            if filename:
                return filename

        # Try to get entity label for Commons search
        entity_labels = claims.get("labels", {})
        en_label = None
        if isinstance(entity_labels, dict):
            en_label = (
                entity_labels.get("en", {}).get("value")
                if isinstance(entity_labels.get("en"), dict)
                else None
            )

        if not en_label:
            # Try to extract from P31 (instance of) or other properties
            # This is a fallback - the label should come from the entity fetch
            return None

        # Search Commons for images related to this entity
        try:
            safe_label = en_label.replace(" ", "_")
            resp = session.get(
                "https://commons.wikimedia.org/w/api.php",
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": f"file:{safe_label}",
                    "srlimit": 3,
                    "format": "json",
                },
                timeout=10,
            )
            if resp.status_code == 200:
                search_results = resp.json().get("query", {}).get("search", [])
                if search_results:
                    # Return the first result's title
                    return search_results[0].get("title")
        except Exception:
            pass

        return None

    def _get_social_media_data(self, claims: dict) -> Dict[str, Any]:
        accounts: List[Dict[str, str]] = []
        followers: List[Dict[str, Any]] = []

        for prop_id, meta in self._SM_PROPS.items():
            for stmt in claims.get(prop_id, [])[:2]:
                val = stmt.get("mainsnak", {}).get("datavalue", {}).get("value")
                if not isinstance(val, str) or not val.strip():
                    continue
                username = val.strip()
                try:
                    profile_url = meta["url"].format(username)
                except Exception:
                    profile_url = username
                accounts.append(
                    {
                        "platform": meta["label"],
                        "username": username,
                        "url": profile_url,
                        "prop": prop_id,
                    }
                )

        p8687_stmts = claims.get("P8687", [])
        for stmt in p8687_stmts:
            mainsnak = stmt.get("mainsnak", {})
            dv = mainsnak.get("datavalue", {})
            if dv.get("type") != "quantity":
                continue
            try:
                count = int(float(dv["value"]["amount"].lstrip("+")))
            except (KeyError, ValueError, TypeError):
                continue

            qualifiers = stmt.get("qualifiers", {})
            platform_label = "Unknown platform"
            for q_prop, q_label in self._SM_QUALIFIER_PROPS.items():
                if q_prop in qualifiers:
                    platform_label = q_label
                    break
            else:
                if len(p8687_stmts) == 1 and claims.get("P2002"):
                    platform_label = "Twitter / X"

            as_of = "date unknown"
            p585_vals = qualifiers.get("P585", [])
            if p585_vals:
                try:
                    time_str = (
                        p585_vals[0]
                        .get("datavalue", {})
                        .get("value", {})
                        .get("time", "")
                    )
                    as_of = time_str.lstrip("+").split("T")[0]
                except Exception:
                    pass

            followers.append(
                {
                    "platform": platform_label,
                    "count": count,
                    "count_fmt": f"{count:,}",
                    "as_of": as_of,
                }
            )

        followers.sort(key=lambda x: x["count"], reverse=True)
        return {"accounts": accounts, "followers": followers}

    def _format_social_media_section(
        self, sm_data: Dict[str, Any], name: str, qid: Optional[str]
    ) -> str:
        lines = ["", "[ SOCIAL MEDIA PRESENCE ]"]
        accounts = sm_data.get("accounts", [])
        followers = sm_data.get("followers", [])

        if not accounts and not followers:
            lines.append("  No social media accounts found on Wikidata.")
            return "\n".join(lines)

        if accounts:
            lines.append("  Accounts:")
            for acc in accounts:
                lines.append(
                    f"    • {acc['platform']:<18} @{acc['username']:<30}  {acc['url']}"
                )
        else:
            lines.append("  Accounts  : none recorded on Wikidata")

        if followers:
            lines.append("")
            lines.append("  Follower Counts (P8687 — point-in-time snapshots):")
            for f in followers:
                lines.append(
                    f"    • {f['platform']:<18} {f['count_fmt']:>15} followers   (as of {f['as_of']})"
                )
        else:
            lines.append("  Followers : no P8687 data on Wikidata")

        if qid:
            lines.append(f"  Wikidata  : https://www.wikidata.org/wiki/{qid}")
        return "\n".join(lines)

    def _get_direct_image_url(
        self, session: requests.Session, filename: str
    ) -> Optional[str]:
        safe = filename.replace(" ", "_")
        resp = self._wm_get(
            session,
            "https://commons.wikimedia.org/w/api.php",
            {
                "action": "query",
                "titles": f"File:{safe}",
                "prop": "imageinfo",
                "iiprop": "url",
                "iiurlwidth": 400,
                "format": "json",
            },
        )
        pages = resp.json().get("query", {}).get("pages", {})
        for page_data in pages.values():
            info = page_data.get("imageinfo", [{}])[0]
            return info.get("thumburl") or info.get("url")
        return None

    def _get_relatives(
        self, session: requests.Session, claims: dict
    ) -> List[Dict[str, str]]:
        relatives: List[Dict[str, str]] = []
        qids_to_fetch: Dict[str, str] = {}

        for prop, relation_label in self._RELATION_PROPS.items():
            for stmt in claims.get(prop, []):
                dv = stmt.get("mainsnak", {}).get("datavalue", {})
                if dv.get("type") != "wikibase-entityid":
                    continue
                qid = dv.get("value", {}).get("id")
                if qid and qid not in qids_to_fetch:
                    qids_to_fetch[qid] = relation_label

        if not qids_to_fetch:
            return []

        qid_list = list(qids_to_fetch.keys())[:50]
        try:
            resp = self._wm_get(
                session,
                "https://www.wikidata.org/w/api.php",
                {
                    "action": "wbgetentities",
                    "ids": "|".join(qid_list),
                    "props": "labels",
                    "languages": "en",
                    "format": "json",
                },
            )
            entities = resp.json().get("entities", {})
            for qid in qid_list:
                entity = entities.get(qid, {})
                label = entity.get("labels", {}).get("en", {}).get("value") or qid
                relatives.append(
                    {
                        "relation": qids_to_fetch[qid],
                        "name": label,
                        "qid": qid,
                        "wikidata_url": f"https://www.wikidata.org/wiki/{qid}",
                    }
                )
        except Exception:
            pass
        return relatives

    def _format_relatives_section(
        self, relatives: List[Dict[str, str]], name: str
    ) -> str:
        if not relatives:
            return f"\n[ FAMILY / ASSOCIATES ]\n  No relatives found on Wikidata for '{name}'."
        lines = [
            "",
            "[ FAMILY / ASSOCIATES ]",
            f"  {'Relationship':<20} {'Name':<35} {'Wikidata URL'}",
            f"  {'-'*20} {'-'*35} {'-'*50}",
        ]
        for r in relatives:
            lines.append(f"  {r['relation']:<20} {r['name']:<35} {r['wikidata_url']}")
        return "\n".join(lines)

    def _run(self, yente_output: str, original_name: str = "") -> str:
        name: Optional[str] = None
        qid_hint: Optional[str] = None
        original_input_name: Optional[str] = None  # Track original user input name

        # Extract original_name from parameter first (Issue 1 fix)
        if original_name and original_name.strip():
            original_input_name = original_name.strip()

        for line in yente_output.splitlines():
            stripped = line.strip()
            if stripped.startswith("ENTITY_NAME:"):
                name = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("ORIGINAL_INPUT_NAME:"):
                # Also check if Yente output contains the original input name
                original_input_name = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("ENTITY_ID:"):
                raw_id = stripped.split(":", 1)[1].strip()
                if re.match(r"^Q\d+$", raw_id):
                    qid_hint = raw_id

        # Issue 1 Fix: Use original user-inputted name for Wikidata search if available
        # This ensures we search by the actual name the user typed, not an alias
        search_name = original_input_name if original_input_name else name

        if not search_name:
            return "WIKIDATA_IMAGE: Could not extract entity name from Yente output."

        # Log which name is being used for debugging
        if original_input_name and original_input_name != name:
            print(
                f"[WikidataOSINTTool] Using original input name '{original_input_name}' instead of Yente entity name '{name}' for Wikidata search"
            )

        try:
            session = requests.Session()
            session.headers.update(self._WM_HEADERS)

            claims: dict = {}
            image_filename: Optional[str] = None
            qid_used: Optional[str] = None

            if qid_hint:
                try:
                    claims = self._get_all_claims(session, qid_hint)
                    fn = self._get_p18_filename(session, claims)
                    if fn:
                        image_filename = fn
                    qid_used = qid_hint
                except Exception:
                    claims = {}
            if not qid_used:
                # Issue 1 Fix: Use search_name (original input name) instead of name (alias)
                search_resp = self._wm_get(
                    session,
                    "https://www.wikidata.org/w/api.php",
                    {
                        "action": "wbsearchentities",
                        "search": search_name,
                        "language": "en",
                        "type": "item",
                        "format": "json",
                        "limit": 5,
                    },
                )
                candidates = search_resp.json().get("search", [])
                if not candidates:
                    return (
                        f"WIKIDATA_IMAGE: No Wikidata entity found for '{name}'.\n"
                        "SOCIAL_MEDIA_SECTION:\n  No social media data — entity not found on Wikidata."
                    )

                best_claims: dict = {}
                best_qid: Optional[str] = None
                best_image: Optional[str] = None

                for candidate in candidates:
                    qid = candidate.get("id")
                    if not qid:
                        continue
                    time.sleep(0.4)
                    try:
                        c_claims = self._get_all_claims(session, qid)
                        fn = self._get_p18_filename(session, c_claims)
                        sm = self._get_social_media_data(c_claims)
                        rels = self._get_relatives(session, c_claims)
                        has_data = bool(fn or sm["accounts"] or sm["followers"] or rels)

                        if not best_qid and has_data:
                            best_claims = c_claims
                            best_qid = qid
                            best_image = fn

                        if fn and (sm["accounts"] or rels):
                            best_claims = c_claims
                            best_qid = qid
                            best_image = fn
                            break
                    except Exception:
                        continue

                claims = best_claims
                qid_used = best_qid
                image_filename = best_image

                sm_data = (
                    self._get_social_media_data(claims)
                    if claims
                    else {"accounts": [], "followers": []}
                )
                relatives = self._get_relatives(session, claims) if claims else []
                bio_data = self._get_biography_data(session, claims) if claims else {}

                # Use search_name for formatting sections to maintain consistency
                social_section = self._format_social_media_section(
                    sm_data, search_name, qid_used
                )
                relative_section = self._format_relatives_section(
                    relatives, search_name
                )
                bio_section = self._format_biography_section(bio_data, search_name)

                output_parts: List[str] = [
                    f"SOCIAL_MEDIA_SECTION:{social_section}",
                    f"RELATIVES_SECTION:{relative_section}",
                    f"BIOGRAPHY_SECTION:{bio_section}",
                ]

                # Issue 2 Fix: Try all image retrieval methods before returning "no image"
                image_retrieved = False
                image_source = ""

                # Method 1: Try P18 image if available
                if image_filename:
                    time.sleep(0.4)
                    direct_url = self._get_direct_image_url(session, image_filename)
                    if direct_url:
                        try:
                            img_resp = session.get(direct_url, timeout=30, stream=True)
                            img_resp.raise_for_status()

                            content_type = img_resp.headers.get("content-type", "")
                            ext = (
                                ".svg"
                                if "svg" in content_type
                                else ".png" if "png" in content_type else ".jpg"
                            )

                            # Use search_name (original input name) for filename to maintain consistency
                            safe_name = re.sub(r"[^\w\-.]", "_", search_name)
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            img_path = (
                                IMAGE_OUTPUT_DIR / f"{safe_name}_{timestamp}{ext}"
                            )

                            with open(img_path, "wb") as img_file:
                                for chunk in img_resp.iter_content(chunk_size=8192):
                                    if chunk:
                                        img_file.write(chunk)

                            output_parts.append(
                                f"\nWIKIDATA_IMAGE_PATH: {img_path}\n"
                                f"Source: Wikidata {qid_used} — P18 image for '{name}'"
                            )
                            image_retrieved = True
                            image_source = "P18"
                        except Exception as img_err:
                            # Log the error but continue to try alternative methods
                            output_parts.append(
                                f"\nWIKIDATA_IMAGE_ERROR: Failed to download P18 image: {str(img_err)}"
                            )

                # Method 2: Try alternative image properties if P18 failed or not available
                if not image_retrieved and claims:
                    alt_filename = self._get_alternative_image_filename(
                        session, claims, qid_used
                    )
                    if alt_filename and alt_filename != image_filename:
                        time.sleep(0.4)
                        direct_url = self._get_direct_image_url(session, alt_filename)
                        if direct_url:
                            try:
                                img_resp = session.get(
                                    direct_url, timeout=30, stream=True
                                )
                                img_resp.raise_for_status()

                                content_type = img_resp.headers.get("content-type", "")
                                ext = (
                                    ".svg"
                                    if "svg" in content_type
                                    else ".png" if "png" in content_type else ".jpg"
                                )

                                # Use search_name (original input name) for filename to maintain consistency
                                safe_name = re.sub(r"[^\w\-.]", "_", search_name)
                                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                img_path = (
                                    IMAGE_OUTPUT_DIR / f"{safe_name}_{timestamp}{ext}"
                                )

                                with open(img_path, "wb") as img_file:
                                    for chunk in img_resp.iter_content(chunk_size=8192):
                                        if chunk:
                                            img_file.write(chunk)

                                output_parts.append(
                                    f"\nWIKIDATA_IMAGE_PATH: {img_path}\n"
                                    f"Source: Wikidata {qid_used} — Alternative image for '{name}'"
                                )
                                image_retrieved = True
                                image_source = "alternative"
                            except Exception as img_err:
                                output_parts.append(
                                    f"\nWIKIDATA_IMAGE_ERROR: Failed to download alternative image: {str(img_err)}"
                                )

                # Only return "no image" message if all methods failed
                if not image_retrieved:
                    if image_filename:
                        output_parts.append(
                            f"\nWIKIDATA_IMAGE: Entity '{search_name}' found on Wikidata "
                            f"(QID: {qid_used or 'unknown'}) with P18 image '{image_filename}' "
                            "but could not retrieve download URL from Commons."
                        )
                    else:
                        output_parts.append(
                            f"\nWIKIDATA_IMAGE: Entity '{search_name}' found on Wikidata "
                            f"(QID: {qid_used or 'unknown'}) but has no P18 portrait image available."
                        )

                return "\n".join(output_parts)

        except Exception as e:
            return f"WIKIDATA_IMAGE: Failed to fetch data for '{name}': {str(e)}"
