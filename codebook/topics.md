# `topic` — what the complaint is about (decision index, Stage 3, v1)

**Derived from the corpus, not from a template.** On 2026-11-23 I read, with names masked by
`scripts/redact.py`, the headnote and the closing order of all 57 distinct NFO Final Determinations,
and the opening complaint section or the order of ~50 FAIS determinations. The FAIS sample was
stratified by the table's `category` (Investments 12, Short-term 12, Property Syndication 6,
Long-term 6, Forex 3, Retirement 3, Medical-Aid 1, Non-FAIS/FSOS 1, blank 2), plus 9 spread by
year from 2005 to 2025. A phrase count over all 543 determinations that have text backs up the
spread (counts are documents that *mention* the phrase, not documents *about* it).

## How a topic is assigned

- `topic` is **the issue the decision turns on**, meaning the question the ombud actually answers.
  It is not the product line. Product line is a separate field, `product_line`, taken from the
  FAIS table's `category`. All NFO determinations are long-term insurance.
- `topics_secondary` holds at most two further issues that the decision also rules on. It is
  optional and never repeats `topic`.
- A document with no ruling (`outcome` is `amendment` or `no_ruling`) gets `topic: null`. The
  issue of an amendment belongs to the determination it amends.
- Precedence, when two terms seem to fit. The first match wins:
  1. `misappropriation_fraud` — the respondent took the money or ran the scheme.
  2. `unlicensed_provider` — the finding turns on the respondent having no licence.
  3. Anything else, by the ratio of the decision.

  The reason for this order: the more specific a finding of wrongdoing, the more a reader needs
  it, and the less it overlaps.

## Vocabulary (17 terms + `other`)

### Advice and conduct of the provider (mainly FAIS)

| term | definition | evidence (documents read) | corpus signal (FAIS / NFO docs) |
|---|---|---|---|
| `advice_suitability` | the advice was not appropriate to the client's needs, circumstances or risk tolerance, or was given without a proper needs analysis or explanation of risk (General Code s8, s7). This **includes replacement advice**: cash in A and buy B. | `fais-det-a7a6c0056598` (cash in and invest in a trust, risk not explained), `fais-det-c66be188f2ab` (asked for risk-free, told "no risks"), `fais-det-be2c81f644c7`, `fais-det-3fe9232597a6`, `fais-det-ab8b6dac65e9`, `fais-det-17d31a0eb83c` (property syndications sold as safe or guaranteed), `fais-det-1b8b21c6c1fd` (replace a life policy, surrender three savings plans), `fais-det-88f215a4b388` (retirement annuity and the risk analysis), `fais-det-3d02e8a7b15f` (retirement money in a private company), `fais-det-6d9db91e40c7`, `fais-det-63e16c23d1a4` (offshore forex scheme sold as safe) | needs-analysis / suitability wording 288 / 4; "guaranteed / safe / no risk" 146 / 0; property syndication 112 / 0 |
| `misappropriation_fraud` | the provider or its representative took, diverted or never invested the client's money, or ran a fraudulent or fictitious scheme | `fais-det-a5b7095a24a1` (a branch manager devised an investment scheme fraudulently), `fais-det-942936a93047` (promised 30% a month, funds lost), `fais-det-1f5e0958ef72` (an adviser moved a client's funds into his own close corporation), `fais-det-cbdb4006c6fc` | misappropriat / fraud / Ponzi / theft 176 / 3 (it includes "fraud" in passing) |
| `unlicensed_provider` | the respondent rendered financial services, or carried on insurance business, without a licence or registration, and that is what the finding turns on. Typically premiums were collected and claims never paid | `fais-det-da0a301a3f01`, `fais-det-09d13ab61347` (held himself out as a short-term insurer, never licensed), `fais-det-a6eebcad25c8`, `fais-det-eb07a67d8b45`, `fais-det-18f1a82cc0ac` (funeral schemes never registered) | not licensed / never registered 101 / 0 |
| `mandate_breach` | the provider acted without, beyond or against the client's instructions, or failed to carry out instructions in time: unauthorised switches, surrenders, paid-up policies, or cover removed or kept against instructions | `fais-det-c79d4b6b9465` (was the mandate executed as soon as reasonably possible), `fais-det-4089dae072f4` (retirement annuities made paid-up against instructions, a new one set up without authority), `fais-det-588ea45bf3ab` (who instructed the removal of cover) | mandate / without consent / contrary to instruction 128 / 6 |
| `fees_and_charges` | the core complaint is undisclosed, excessive or wrongly levied costs, commission or penalties | `fais-det-9838ccf9e908` (costs of R31 920 described as "nominal") | commission / fees / charges 220 / 5 (most are incidental, so this is a rare primary topic) |
| `intermediary_cover_failure` | a broker or intermediary failed to arrange, renew, update or correctly specify cover (including under-insurance), so a claim failed or was reduced | `fais-det-c21597666d38` (policy not updated after a car was sold), `fais-det-bf52782aaa13` (game-animal cover not renewed), `fais-det-50f92162b5d5` (sum insured not updated, so average applied), `fais-det-290643a8a628`, `fais-det-ddd1ec1272c9` | failed to arrange or renew, under-insured, sum insured 41 / 5 |
| `sale_disclosure` | at the point of sale, the product's nature, terms or conditions were misrepresented or not disclosed, and the question is what the buyer agreed to, not whether advice was suitable: "no consensus", accidental cover sold as life cover, a security condition never mentioned | `fais-det-fe7193dd109d` (immobiliser condition not disclosed in a telephone sale), NFO cases 42, 47, 50, 51, 53 (`nfo-5597`, `nfo-5627`, `nfo-5640`, `nfo-5641`, `nfo-5643`) | — |

### Claims and the policy (both offices; most of NFO)

| term | definition | evidence | corpus signal |
|---|---|---|---|
| `claim_not_paid` | a claim was not paid, or paid late, and no specific contractual defence is in dispute. This covers plain non-payment, an insurer refusing claims because of its dispute with a binder holder, and funeral claims never paid | `fais-det-7f82061df71b`, `fais-det-3294945dac96`, `fais-det-194b31edce97` (2010: the insurer refused every claim placed through one binder holder, one of a mass of identical complaints), `fais-det-cf6db343bfa5`, `fais-det-0b57feb5bc19`, `fais-det-5fced554b462`, `fais-det-df08d4efe364` (2025 funeral claims unpaid despite undertakings) | binder / cell 73 / 1; repudiated or refused to pay 112 / 25 |
| `non_disclosure` | the claim was declined, or the policy avoided, because the insured did not disclose information, or misrepresented it, at application | NFO cases 2, 7, 48 (`nfo-5481`, `nfo-5499`, `nfo-4252`); `fais-det-bab03d430019` (medical-scheme membership application) | 68 / 8 |
| `exclusion_clause` | the claim was declined under an exclusion: a pre-existing condition, suicide, a named exclusion, or the risk having materialised before cover began | NFO cases 9, 19, 46, 49, 56 (`nfo-5511`, `nfo-4230`, `nfo-5626`, `nfo-4253`, `nfo-5862`) | 66 / 13 |
| `late_notification` | the claim or notice was lodged outside a contractual time limit, and whether that can be condoned (the NFO's equity jurisdiction) | NFO cases 5, 8, 12, 13, 16, 25 (`nfo-5497`, `nfo-5500`, `nfo-4228`, `nfo-5517`, `nfo-4229`, `nfo-4238`) | 13 / 10 |
| `policy_interpretation` | what the policy wording means: definitions (dependant, cousin, extended family, adopted child, insurable interest), commencement, waiting periods, benefit calculation, overlapping cover | NFO cases 6, 10, 21, 27, 28, 34, 38, 39, 41, 55, 58 (`nfo-5498`, `nfo-5512`, `nfo-5541`, `nfo-5559`, `nfo-4249`, `nfo-5570`, `nfo-5593`, `nfo-5594`, `nfo-5596`, `nfo-5470`, `nfo-6787`); `fais-det-f507db46d649` (mechanical-breakdown benefit wording) | 53 / 14 |
| `disability_assessment` | whether the insured meets the definition of disability or incapacity (own occupation or alternative occupation), and the termination, review or level of disability or income benefits | NFO cases 3, 15, 23, 32, 40, 44, 54, 57 (`nfo-5482`, `nfo-5519`, `nfo-5543`, `nfo-5569`, `nfo-5595`, `nfo-4251`, `nfo-4254`, `nfo-5863`) | 18 / 22 |
| `lapse_and_cancellation` | the policy, or cover on one life, lapsed, was cancelled or terminated, or was refused reinstatement | NFO cases 1, 17, 20, 33, 37, 52 (`nfo-4211`: the insurer ended disability cover for unpaid premiums after scheme membership ceased; I had listed it under `disability_assessment` from its headnote, and the hand check in `notes/decision-sample.md` moved it. Also `nfo-5533`, `nfo-5540`, `nfo-5566`, `nfo-5592`, `nfo-5642`) | lapse / cancel / reinstate 197 / 22 (mostly incidental in FAIS) |
| `service_and_compensation` | poor service, administrative error or delay, compensation for distress and inconvenience, interest on late payment | NFO cases 4, 22, 26, 29, 31, 36, 45 (`nfo-4222`, `nfo-5542`, `nfo-4248`, `nfo-5565`, `nfo-5568`, `nfo-5591`, `nfo-5625`) | 1 / 8 |
| `beneficiary_and_cession` | who is entitled to the money: beneficiary nominations, cession, payment to the wrong person | NFO cases 11, 14 (`nfo-4227`, `nfo-5518`) | 77 / 12 (mostly incidental) |
| `other` | fits none of the above. The codebook lists every such document below, and none is forced into a term | see below | — |

## Documents that fit nothing (`other`), so far

- `nfo-5534` (NFO case 18, 2014). The insurer rejected a claim as **fraudulent** because of false
  declarations on the claim form, and the rejection was set aside on appeal. This is not
  non-disclosure at application, and not an exclusion. It is one case in 57. A
  `fraudulent_claim_defence` term would be justified only if more cases like it turn up in the
  full run.
- `nfo-4250` (NFO case 35, 2019). The **in duplum rule on a policy loan**, meaning interest on a
  loan against the policy. It sits nearest `policy_interpretation`, but the question is a
  common-law limit on interest, not the policy's wording. I would classify it `other` rather
  than force it.

## What this vocabulary assumes, and where it is weak

- **`advice_suitability` will dominate FAIS.** Investments (190 documents) and Property
  Syndication (87) are mostly the same story: a failed scheme, and a complaint against the adviser
  who sold it. The term is correct, but it is broad. A later version may split out
  `property_syndication` as a scheme marker rather than as a topic.
- **`advice_suitability`, `sale_disclosure` and `misappropriation_fraud` overlap.** Property
  syndication cases often allege all three. The precedence rule above decides the primary topic,
  and `topics_secondary` keeps the rest. Expect the most model disagreement here.
- **Mass-complaint clusters** (the 2010 binder dispute, the mass funeral non-payments) make
  `claim_not_paid` look bigger than the variety of disputes behind it. Count respondents and
  clusters before reading topic shares as trends.
- **NFO and FAIS are not comparable on topic.** NFO publishes a curated set of case reports
  about the insurer's claim decision. FAIS publishes its formal determinations about advisers and
  intermediaries. The claims family is therefore NFO-heavy by construction, not because
  consumers complain differently.
