# ESG Standards Knowledge Base for Greenwashing Screening

This knowledge base is the retrieval corpus of the GreenWash-Screener Agentic RAG pipeline.
Each `##` section is a standard family and each `###` subsection is an indexed chunk.
The agent retrieves the most relevant chunks to cross-examine every corporate environmental claim.
Content is a condensed educational summary of public standards; always refer to the official texts for compliance work.

## GRI 305: Emissions (Global Reporting Initiative)

### GRI 305 Overview and Reporting Principles
GRI 305 (Emissions 2016) requires organizations to report greenhouse gas (GHG) emissions in metric tonnes of CO2 equivalent (tCO2e) following the GHG Protocol Corporate Standard. Reporters must state the gases included (CO2, CH4, N2O, HFCs, PFCs, SF6, NF3), the base year and rationale for choosing it, the source of emission factors and global warming potential (GWP) rates, and the consolidation approach (equity share, financial control or operational control). Disclosures without units, base year or consolidation approach are incomplete under GRI. GRI 102: Climate Change (2025) and GRI 103: Energy (2025) will supersede GRI 305 and GRI 302 for reporting periods starting 1 January 2027 and add transition plan and just transition requirements.

### GRI 305-1 Direct (Scope 1) GHG Emissions
GRI 305-1 requires gross direct (Scope 1) GHG emissions in tCO2e from sources owned or controlled by the organization: stationary combustion, process emissions, fugitive emissions and company vehicles. Biogenic CO2 must be reported separately. For semiconductor manufacturers, fluorinated process gases (PFCs, NF3, SF6, HFCs) used in etching and chamber cleaning are often the dominant Scope 1 source and must be included. A claim about Scope 1 performance must disclose absolute tCO2e, the base year and the percentage change.

### GRI 305-2 Energy Indirect (Scope 2) GHG Emissions
GRI 305-2 requires gross location-based Scope 2 emissions and, where the organization has contractual instruments (renewable energy certificates, power purchase agreements), market-based Scope 2 emissions as well. Claims of "100% renewable electricity" must be supported by market-based accounting, the type of instrument (PPA, unbundled REC, green tariff) and should disclose the location-based figure to avoid overstating real grid decarbonization. Unbundled certificates without additionality are a known greenwashing vector.

### GRI 305-3 Other Indirect (Scope 3) GHG Emissions
GRI 305-3 requires gross other indirect (Scope 3) emissions in tCO2e, the categories and activities included, and the methodology. The GHG Protocol defines 15 Scope 3 categories (e.g., Category 1 Purchased goods and services, Category 4 Upstream transportation, Category 11 Use of sold products, Category 12 End-of-life treatment). For technology hardware and fabless chip designers, Scope 3 commonly represents more than 80-90% of total emissions. Omitting material Scope 3 categories while highlighting operational achievements is classified as cherry-picking.

### GRI 305-4 GHG Emissions Intensity
GRI 305-4 requires the GHG emissions intensity ratio and the organization-specific denominator (e.g., tCO2e per unit of production, per 12-inch equivalent wafer mask layer, per million USD revenue). Intensity improvements can coexist with rising absolute emissions; a claim that relies only on intensity without disclosing absolute emissions is a partial disclosure and a grey-zone risk.

### GRI 305-5 Reduction of GHG Emissions
GRI 305-5 requires GHG emissions reduced as a direct result of reduction initiatives, in tCO2e, the base year or baseline, the scopes in which reductions took place, and the standards and methodologies used. Reductions from divestment, outsourcing or reduced production output must not be presented as reduction initiatives. Carbon offsets must be reported separately from reductions.

### GRI 302 Energy and GRI 303 Water (Companion Standards)
GRI 302-1 requires total energy consumption within the organization in joules or multiples (GJ, TJ) or MWh, split by renewable and non-renewable sources. GRI 302-4 covers reduction of energy consumption. GRI 303-3 requires total water withdrawal in megalitres by source and in areas with water stress; GRI 303-5 requires total water consumption. Water recycling claims for fabs should state the recycled volume and the recycling rate definition.

### GRI 2-5 External Assurance
GRI 2-5 requires the organization to describe its policy and practice for seeking external assurance, the assurance provider, the standard used (e.g., ISAE 3000, ISAE 3410, AA1000AS v3, ISO 14064-3), the level of assurance (limited or reasonable), and any limitations. A sustainability report claiming to be prepared "in accordance with GRI" must include a GRI content index that maps each disclosure to its location.

## SASB Standards: Semiconductors, Hardware and Electronic Manufacturing Services

### SASB Semiconductors (TC-SC) Materiality Map
The SASB Semiconductors Standard (TC-SC) identifies the following financially material environmental topics: Greenhouse Gas Emissions (TC-SC-110a.1 gross global Scope 1 emissions and amount of total emissions from perfluorinated compounds; TC-SC-110a.2 discussion of long-term and short-term strategy to manage Scope 1 emissions and reduction targets), Energy Management in Manufacturing (TC-SC-130a.1 total energy consumed, percentage grid electricity, percentage renewable), Water Management (TC-SC-140a.1 total water withdrawn, total water consumed, percentage of each in regions with High or Extremely High Baseline Water Stress), Waste Management (TC-SC-150a.1 amount of hazardous waste from manufacturing and percentage recycled), and Product Lifecycle Management (TC-SC-410a.2 processor energy efficiency at a system level).

### SASB TC-SC-110a Greenhouse Gas Emissions for Chipmakers
Semiconductor fabrication uses high-GWP fluorinated gases such as CF4, C2F6, NF3 and SF6, with GWPs between 6,500 and 23,500 times CO2. SASB requires separate disclosure of PFC emissions, and investors expect abatement system coverage (point-of-use scrubbers, remote plasma cleaning), destruction removal efficiency and absolute reduction targets. A chipmaker that reports renewable electricity progress but no PFC emissions omits its most material Scope 1 lever.

### SASB Hardware (TC-HW) and EMS and ODM (TC-ES)
The SASB Hardware Standard (TC-HW) covers Product Security, Employee Diversity, Product Lifecycle Management (TC-HW-410a.1 percentage of products containing IEC 62474 declarable substances; TC-HW-410a.4 percentage of eligible products meeting ENERGY STAR or EPEAT criteria), Supply Chain Management (TC-HW-430a.1 percentage of Tier 1 supplier facilities audited in the RBA Validated Audit Process) and Materials Sourcing (TC-HW-440a.1 management of critical materials risks). The Electronic Manufacturing Services and Original Design Manufacturing Standard (TC-ES) requires energy (TC-ES-130a.1), water (TC-ES-140a.1), hazardous waste (TC-ES-150a.1), product end-of-life weight recovered (TC-ES-410a.1) and RBA supply-chain audit metrics (TC-ES-430a.1).

### SASB Water Stress and Taiwan Fab Context
Semiconductor fabs require large volumes of ultra-pure water (UPW). SASB TC-SC-140a.1 requires the share of water withdrawn and consumed in regions with High or Extremely High Baseline Water Stress (WRI Aqueduct). Taiwan experienced a severe drought in 2021, making water recycling rates, reclaimed water usage and process water reuse highly material for Taiwanese foundries. Claims about water stewardship should report megalitres withdrawn, the recycling rate and the water-stress exposure.

## TCFD: Task Force on Climate-related Financial Disclosures

### TCFD Four Pillars Framework
The TCFD recommendations (2017, updated guidance 2021) are structured in four pillars and 11 recommended disclosures. Governance: board oversight and management's role in climate-related risks and opportunities. Strategy: climate-related risks and opportunities over short, medium and long term, their impact on business, strategy and financial planning, and resilience of the strategy under different scenarios including a 2°C or lower scenario. Risk Management: processes for identifying, assessing and managing climate risks and their integration into overall risk management. Metrics and Targets: metrics used to assess climate risks, Scope 1, Scope 2 and if appropriate Scope 3 GHG emissions, and targets with performance against them. Since 2024 the IFRS Foundation monitors climate disclosures and the TCFD recommendations are fully incorporated into ISSB IFRS S2.

### TCFD Metrics and Targets Requirements
Under TCFD Metrics and Targets, organizations should disclose cross-industry metrics: absolute Scope 1, Scope 2 and Scope 3 emissions, emissions intensity, the amount and extent of assets vulnerable to transition and physical risks, climate-related opportunities, capital deployment toward climate risks and opportunities, internal carbon prices, and the proportion of executive remuneration linked to climate considerations. Targets should specify the time frame, the base year, interim targets and key performance indicators used to assess progress.

### TCFD Scenario Analysis and Strategy Resilience
TCFD Strategy (c) asks companies to describe the resilience of their strategy under different climate-related scenarios, including a 2°C or lower scenario. Credible disclosure names the scenarios used (e.g., IEA Net Zero Emissions by 2050, NGFS scenarios, IPCC SSP1-2.6 and SSP5-8.5), the time horizons, and the quantified financial impacts such as carbon pricing costs, electricity price increases or physical damage to fabs from typhoons, floods and drought.

## ISSB: IFRS S1 and IFRS S2 Sustainability Disclosure Standards

### IFRS S1 General Requirements for Sustainability-related Financial Information
IFRS S1 (issued June 2023, effective for annual periods beginning on or after 1 January 2024 where adopted) requires an entity to disclose material information about all sustainability-related risks and opportunities that could reasonably be expected to affect its cash flows, access to finance or cost of capital over the short, medium or long term. The core content follows the TCFD architecture (governance, strategy, risk management, metrics and targets). IFRS S1 requires connectivity between sustainability disclosures and the financial statements, and refers entities to SASB Standards as a source of guidance to identify industry-specific disclosure topics. Taiwan's Financial Supervisory Commission (FSC) has adopted a phased roadmap for listed companies to apply IFRS Sustainability Disclosure Standards starting from fiscal year 2026, beginning with the largest listed companies.

### IFRS S2 Climate-related Disclosures: GHG Emissions (Paragraph 29)
IFRS S2 paragraph 29(a) requires absolute gross GHG emissions for the reporting period, in metric tonnes of CO2 equivalent, classified as Scope 1, Scope 2 (location-based, with information on contractual instruments) and Scope 3, measured in accordance with the GHG Protocol Corporate Standard. Scope 3 disclosure must include the categories included per the GHG Protocol Corporate Value Chain (Scope 3) Standard. A transition relief allows entities not to disclose Scope 3 in the first annual reporting period, but Scope 3 is mandatory afterwards. Paragraph 29 also requires cross-industry metrics on transition risks, physical risks, climate opportunities, capital deployment, internal carbon prices and remuneration.

### IFRS S2 Climate-related Targets (Paragraphs 33-36)
IFRS S2 paragraphs 33 to 36 require, for each climate-related target: the metric used, the specific quantitative or qualitative objective, the part of the entity to which it applies, the period over which it applies, the base period from which progress is measured, any milestones and interim targets, whether it is an absolute or intensity target, how the latest international agreement on climate change informed it, whether it has been validated by a third party (e.g., the Science Based Targets initiative), and for GHG targets which gases and scopes are covered and the planned use of carbon credits. A net-zero target without base period, interim milestones or carbon credit disclosure fails IFRS S2.

### IFRS S2 Transition Plans and Capital Deployment
IFRS S2 paragraph 14 requires information about the entity's climate-related transition plan, including key assumptions, dependencies, current and anticipated changes to the business model, direct and indirect mitigation and adaptation efforts, and how these efforts are resourced. Capital expenditure (CAPEX), financing or investment deployed toward climate-related risks and opportunities must be disclosed. Aspirational statements without resourcing evidence are not decision-useful.

### Industry-based Guidance on Implementing IFRS S2 (Semiconductors)
The ISSB's Industry-based Guidance on implementing IFRS S2, derived from SASB, includes metrics for the Semiconductors industry: gross global Scope 1 emissions and amount from perfluorinated compounds, discussion of strategy to manage Scope 1 emissions, total energy consumed with percentage grid electricity and renewable, and water withdrawn and consumed in high water-stress regions. These metrics make PFC abatement, renewable procurement and water management central to the climate disclosures of chipmakers.

## EU CSRD, ESRS E1 and EU Green Claims Rules

### EU CSRD and ESRS E1 Climate Change
The Corporate Sustainability Reporting Directive (CSRD, Directive (EU) 2022/2464) requires in-scope companies to report under the European Sustainability Reporting Standards (ESRS) using double materiality (impact and financial). ESRS E1 Climate Change disclosures include: E1-1 transition plan for climate change mitigation compatible with limiting warming to 1.5°C, E1-4 targets related to climate change mitigation and adaptation, E1-5 energy consumption and mix, E1-6 gross Scope 1, 2, 3 and total GHG emissions, E1-7 GHG removals and mitigation projects financed through carbon credits, E1-8 internal carbon pricing and E1-9 anticipated financial effects. CSRD mandates limited assurance by an independent auditor. The 2025 Omnibus simplification package postponed later reporting waves and proposed narrowing the scope, but non-EU groups with large EU turnover remain potentially in scope.

### EU Empowering Consumers for the Green Transition Directive (2024/825)
Directive (EU) 2024/825, applicable from 27 September 2026, amends the Unfair Commercial Practices Directive to ban: generic environmental claims such as "environmentally friendly", "eco-friendly", "green", "nature's friend", "climate friendly", "carbon friendly", "energy efficient" or "biodegradable" when the trader cannot demonstrate recognised excellent environmental performance; claims that a product has a neutral, reduced or positive impact on the environment based on greenhouse gas offsetting; sustainability labels not based on a certification scheme or established by public authorities; and environmental claims about the entire product or business when they concern only a certain aspect. Future environmental performance claims (e.g., "net zero by 2050") must be supported by a detailed and realistic implementation plan with measurable, time-bound targets, verified by an independent third-party expert.

### EU Green Claims Directive Proposal (Substantiation Principles)
The European Commission's 2023 Green Claims Directive proposal set out substantiation requirements for explicit environmental claims: claims must be based on widely recognised scientific evidence, consider the full life cycle, identify whether improvements are significant, disclose whether offsets are used, and be verified ex-ante by an accredited third party. Although the legislative process stalled in 2025, these substantiation principles remain the reference benchmark for credible green claims and are used by regulators such as the UK CMA Green Claims Code and the US FTC Green Guides.

## Science Based Targets, GHG Protocol and Assurance Practice

### SBTi Corporate Net-Zero Standard
The Science Based Targets initiative (SBTi) Corporate Net-Zero Standard requires: near-term targets covering 5 to 10 years from submission, aligned with 1.5°C (around 4.2% annual linear reduction for Scope 1 and 2); a near-term Scope 3 target when Scope 3 represents 40% or more of total emissions, covering at least 67% of Scope 3; long-term targets of at least 90% absolute reduction by 2050 at the latest; and neutralization of residual emissions with permanent removals. Carbon credits cannot be counted toward near-term or long-term reduction targets. A "validated" status means SBTi has reviewed the targets; a "committed" status only means the company has pledged to set targets within 24 months.

### GHG Protocol Scope Definitions
The GHG Protocol defines Scope 1 as direct emissions from owned or controlled sources, Scope 2 as indirect emissions from purchased electricity, steam, heating and cooling, and Scope 3 as all other indirect emissions in the value chain, both upstream and downstream, in 15 categories. Materiality screening must justify excluded categories. For electronics brands, Category 1 (purchased goods, e.g., wafers, chips, displays) and Category 11 (use of sold products, e.g., electricity consumed by GPUs and servers) usually dominate.

### Third-Party Assurance Levels and Standards
Limited assurance provides a negative-form conclusion ("nothing has come to our attention") based on inquiry and analytical procedures; reasonable assurance provides a positive-form opinion comparable to a financial audit. Common assurance standards are ISAE 3000 (Revised), ISAE 3410 (GHG statements), AA1000AS v3, ISO 14064-3 and the new ISSA 5000 (issued by IAASB in 2024). Recognised assurance providers include Deloitte, PwC, KPMG, EY, SGS, DNV, Bureau Veritas, BSI and TÜV. A claim is only considered externally verified if the assured scope explicitly covers the metric being claimed.

### Carbon Neutrality, Offsets and Renewable Energy Certificates
"Carbon neutral" or "climate neutral" claims based mainly on purchased offsets are high-risk: voluntary carbon credits can lack additionality, permanence or suffer double counting. Best practice (ISO 14068-1:2023 on carbon neutrality) requires prioritising absolute reductions, transparent disclosure of offset quantity, type and registry, and a reduction pathway. Unbundled renewable energy certificates (RECs/T-RECs in Taiwan) purchased without additionality do not reduce location-based emissions and should be disclosed separately from physical or virtual PPAs.
