# JourneyIQ — Customer Journey Analytics

**Understand every journey. Eliminate every friction.**

JourneyIQ is a customer journey analytics application designed to help businesses understand how customers interact with their digital platforms, identify conversion drop-offs, discover friction points, and monitor journey quality through interactive dashboards.

**Live Demo:** https://yotta-journey.vercel.app/  
**GitHub Repository:** https://github.com/eswarrithik/yotta-journey

---

## 📌 Project Overview

Customers interact with businesses through websites, applications, product pages, shopping carts, purchases, and customer support. Understanding these interactions helps businesses improve customer experience and increase conversions.

JourneyIQ provides a dashboard-based approach to analyzing customer journey data. It organizes journey insights into business-friendly visualizations so that users can explore conversion funnels, friction points, channel performance, and data quality.

## 🎯 Objectives

- Understand customer interactions across digital touchpoints.
- Analyze customer journey funnels and conversion drop-offs.
- Identify pages and journey stages where customers experience friction.
- Compare performance across acquisition channels.
- Monitor anomalies and data quality issues.
- Present customer journey insights through an interactive dashboard.

## ✨ Key Features

### 1. Executive Overview
Displays high-level journey metrics and an overview of customer activity.

### 2. Customer Journey Funnel
Helps visualize customer progression through journey stages and identify potential drop-offs.

### 3. Friction Analysis
Provides a dedicated view for investigating journey bottlenecks and potential customer experience issues.

### 4. Channel Analysis
Organizes journey analysis by channel to help compare customer acquisition and engagement patterns.

### 5. Anomaly Monitoring
Provides a dashboard section for examining unusual journey activity and potential data anomalies.

### 6. Data Quality
Provides a dedicated section for reviewing the quality and reliability of journey data.

### 7. Data Export
The dashboard provides CSV and JSON export options for working with available data.

> Note: Dashboard sections and export controls do not by themselves prove that every underlying analytics, anomaly-detection, or data-generation requirement is implemented. See the verification checklist below.

## 🛠️ Technology Stack

| Technology | Purpose |
|---|---|
| React.js | User interface |
| TypeScript / JavaScript | Application logic |
| Vite | Development server and build tooling |
| CSS | Dashboard styling |
| Vercel | Application deployment |
| Git and GitHub | Version control and source-code hosting |

The exact technologies used by the data-processing layer should be added after verifying the source code.

## 🏗️ Customer Journey Data Model

The project assignment defines the following core entities for representing customer journeys:

1. **Customer** — Customer profile and identity.
2. **Session** — A customer's visit or interaction session.
3. **JourneyEvent** — An individual action performed during a journey.
4. **Page** — A website or application page.
5. **Product** — A product viewed or purchased by a customer.
6. **Cart** — Shopping cart activity.
7. **Order** — Purchase and conversion information.
8. **SupportTicket** — Customer support interactions.
9. **Experiment** — Experiment or A/B testing information.
10. **JourneyOutcome** — The final outcome of a customer journey.

These entities should be connected through appropriate primary keys, foreign keys, and relationships in the implemented data model.

## 📊 Analytics and Data Quality Requirements

The assignment's target capabilities include:

- Customer journey event processing and timestamp handling.
- Sessionization using a 30-minute inactivity threshold.
- Consent-aware identity stitching.
- Funnel and conversion analysis.
- Reproducible synthetic data generation.
- Detection and labelling of data anomalies.
- Data validation and quality checks.
- CSV, JSON, and SQL data exports.
- Automated tests and reproducibility verification.

The implementation status of each capability should be confirmed against the source code and test results before describing it as complete.

## 🚀 Running the Frontend Locally

### Prerequisites

- Node.js
- npm
- Git

### Installation

Clone the repository:

```bash
git clone https://github.com/eswarrithik/yotta-journey.git
cd yotta-journey
```

Install dependencies:

```bash
npm install
```

Start the development server:

```bash
npm run dev
```

Open the local URL printed in the terminal by Vite.

### Build the Application

```bash
npm run build
```

### Run Linting

```bash
npm run lint
```

Run only the commands supported by the repository's current `package.json`.

## 🌐 Deployment

The application is deployed on Vercel.

Live application: https://yotta-journey.vercel.app/

The source code is hosted on GitHub, making the project accessible for review and further development.

## 🧪 Verification Checklist

Before submitting the assignment, verify each item against the actual implementation.

- [ ] All ten entities are implemented with valid relationships.
- [ ] The starter dataset contains approximately 100 sessions and 2,000 events.
- [ ] The full-scale generator supports 100,000 sessions and 2 million events.
- [ ] Synthetic data generation uses a fixed seed of `20261022`.
- [ ] Event timestamps and ingestion timestamps are handled correctly.
- [ ] Sessionization uses the required 30-minute inactivity threshold.
- [ ] Identity stitching respects consent.
- [ ] All four required anomaly types are generated and labelled.
- [ ] Anomaly ground truth is stored separately from ordinary event data.
- [ ] Funnel metrics and journey outcomes are validated.
- [ ] CSV, JSON, and SQL exports work as required.
- [ ] Data dictionary and dataset manifest are provided.
- [ ] Automated tests pass.
- [ ] Repeated generation with the same seed produces reproducible results.

Only mark an item as complete after verifying it.

## 🔮 Future Enhancements

- Real-time customer journey monitoring.
- Advanced journey segmentation.
- Predictive customer drop-off analysis.
- Experiment performance comparisons.
- Additional analytics and reporting capabilities.

## 👨‍💻 Author

**Eswar Rithik**

MCA Graduate | Python Development | Generative AI | Data Analytics

GitHub: https://github.com/eswarrithik

Portfolio: https://eswarrithik.github.io/

---

*JourneyIQ — Turning customer journey data into actionable insights.*
