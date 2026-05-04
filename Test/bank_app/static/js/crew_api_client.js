/**
 * CrewAI API Client - Simplified wrapper for the new generic /api/run-crew/ endpoint
 *
 * This module provides a simple, consistent API for calling all CrewAI crews.
 * Replaces the need for multiple fetch calls to different endpoints.
 *
 * Usage:
 *   // Run analysis crew
 *   const result = await CrewAI.runCrew('analysis', {
 *     query: 'What are the best FD rates?',
 *     region: 'India'
 *   });
 *
 *   // Run credit risk crew
 *   const result = await CrewAI.runCrew('credit_risk', {
 *     query: JSON.stringify({applicant_income: 600000, credit_score: 720})
 *   });
 *
 *   // Legacy wrapper for backward compatibility
 *   const result = await CrewAI.runAnalysisCrew('What are FD rates?', 'India');
 */

(function (global) {
  "use strict";

  const CrewAI = {
    /**
     * Base URL for the generic crew endpoint
     */
    baseUrl: "/api/run-crew/",

    /**
     * Execute a crew with the given type and parameters
     * @param {string} crewType - The type of crew to run (e.g., 'analysis', 'router', 'credit_risk')
     * @param {Object} params - Parameters to pass to the crew
     * @returns {Promise<Object>} - The response from the API
     */
    async runCrew(crewType, params = {}) {
      const payload = {
        crew_type: crewType,
        query: params.query || "",
        region: params.region || "India",
        ...(params.additional_params || {}),
      };

      const response = await fetch(this.baseUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": this._getCSRFToken(),
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({ error: "Unknown error" }));
        throw new Error(error.error || `HTTP error! status: ${response.status}`);
      }

      return response.json();
    },

    /**
     * Get CSRF token from cookie
     * @private
     */
    _getCSRFToken() {
      const name = "csrftoken";
      let cookieValue = null;
      if (document.cookie && document.cookie !== "") {
        const cookies = document.cookie.split(";");
        for (let i = 0; i < cookies.length; i++) {
          const cookie = cookies[i].trim();
          if (cookie.substring(0, name.length + 1) === name + "=") {
            cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
            break;
          }
        }
      }
      return cookieValue || "";
    },

    // =============================================================================
    // LEGACY WRAPPER METHODS - For backward compatibility during migration
    // These call runCrew() with the appropriate crew_type
    // =============================================================================

    /**
     * Run Router Crew - Intelligent query routing
     * @param {string} userQuery - The user's query
     * @param {string} region - The region (default: 'India')
     */
    async runRouterCrew(userQuery, region = "India") {
      return this.runCrew("router", { query: userQuery, region });
    },

    /**
     * Run Analysis Crew - General data analysis
     * @param {string} userQuery - The user's query
     * @param {string} region - The region (default: 'India')
     */
    async runAnalysisCrew(userQuery, region = "India") {
      return this.runCrew("analysis", { query: userQuery, region });
    },

    /**
     * Run Research Crew - Market research
     * @param {string} userQuery - The user's query
     * @param {string} region - The region (default: 'India')
     */
    async runResearchCrew(userQuery, region = "India") {
      return this.runCrew("research", { query: userQuery, region });
    },

    /**
     * Run Database Crew - SQL query generation
     * @param {string} userQuery - The user's query
     */
    async runDatabaseCrew(userQuery) {
      return this.runCrew("database", { query: userQuery });
    },

    /**
     * Run Visualization Crew - Chart generation
     * @param {string} userQuery - The user's query
     * @param {string} dataContext - The data context
     */
    async runVisualizationCrew(userQuery, dataContext) {
      return this.runCrew("visualization", { query: userQuery, data_context: dataContext });
    },

    /**
     * Run Credit Risk Crew - Loan approval analysis
     * @param {string} borrowerJson - JSON string with borrower data
     */
    async runCreditRiskCrew(borrowerJson) {
      return this.runCrew("credit_risk", { query: borrowerJson });
    },

    /**
     * Run Loan Creation Crew - Loan application processing
     * @param {string} borrowerContext - Borrower context
     */
    async runLoanCreationCrew(borrowerContext) {
      return this.runCrew("loan_creation", { query: borrowerContext });
    },

    /**
     * Run Mortgage Analytics Crew - Mortgage calculations
     * @param {string} borrowerJson - JSON string with borrower data
     */
    async runMortgageAnalyticsCrew(borrowerJson) {
      return this.runCrew("mortgage_analytics", { query: borrowerJson });
    },

    /**
     * Run AML Crew - Compliance verification
     * @param {string} clientDataJson - JSON string with client data
     */
    async runAmlCrew(clientDataJson) {
      return this.runCrew("aml", { query: clientDataJson });
    },

    /**
     * Run FD Advisor Crew - FD rate analysis
     * @param {string} userQuery - The user's query
     * @param {string} userEmail - User's email (optional)
     * @param {number} userId - User's ID (optional)
     */
    async runFdAdvisorCrew(userQuery, userEmail = "", userId = null) {
      return this.runCrew("fd_advisor", { query: userQuery, user_email: userEmail, user_id: userId });
    },

    /**
     * Run FD Template Crew - FD template generation
     * @param {Object} fdData - FD data object
     */
    async runFdTemplateCrew(fdData) {
      return this.runCrew("fd_template", { query: JSON.stringify(fdData) });
    },
  };

  // Export to global scope
  global.CrewAI = CrewAI;
})(window);
