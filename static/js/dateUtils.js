/**
 * Date utility functions for timezone conversion
 * Single Responsibility: Only handles date formatting and timezone conversion
 */

/**
 * Format UTC datetime string to Taiwan timezone display
 * @param {string} utcDateString - UTC datetime string (e.g., "2026-01-12T05:01:04.117873")
 * @param {string} timezone - Target timezone (default: 'Asia/Taipei')
 * @returns {string} Formatted date string (e.g., "1/12 13:01")
 */
function formatToTimezone(utcDateString, timezone = 'Asia/Taipei') {
    if (!utcDateString) {
        return '-';
    }

    // Ensure UTC parsing by appending 'Z' if no timezone indicator present
    let dateStr = utcDateString;
    if (!dateStr.endsWith('Z') && !dateStr.includes('+') && !dateStr.includes('-', 10)) {
        dateStr = dateStr + 'Z';
    }

    const date = new Date(dateStr);
    
    // Check for invalid date
    if (isNaN(date.getTime())) {
        return '-';
    }

    // Format to target timezone
    const formatted = date.toLocaleString('zh-TW', {
        month: 'numeric',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
        timeZone: timezone
    });

    // Convert "1月12日 13:01" to "1/12 13:01"
    return formatted
        .replace(/(\d+)月(\d+)日/, '$1/$2')
        .replace(',', '')
        .trim();
}

// Export for testing (Node.js) and browser usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { formatToTimezone };
}
