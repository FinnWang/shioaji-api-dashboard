/**
 * Tests for dateUtils.js
 * Run with: node static/js/dateUtils.test.js
 */

const { formatToTimezone } = require('./dateUtils');

// Simple test runner
let passed = 0;
let failed = 0;

function test(name, fn) {
    try {
        fn();
        console.log(`✓ ${name}`);
        passed++;
    } catch (error) {
        console.log(`✗ ${name}`);
        console.log(`  Expected: ${error.expected}`);
        console.log(`  Actual:   ${error.actual}`);
        failed++;
    }
}

function assertEqual(actual, expected) {
    if (actual !== expected) {
        const error = new Error('Assertion failed');
        error.actual = actual;
        error.expected = expected;
        throw error;
    }
}

// Test cases
test('should convert UTC morning time to Taiwan afternoon', () => {
    // UTC 05:01 = Taiwan 13:01 (UTC+8)
    const result = formatToTimezone('2026-01-12T05:01:04.117873');
    assertEqual(result, '1/12 13:01');
});

test('should handle UTC midnight to Taiwan morning', () => {
    // UTC 00:00 = Taiwan 08:00
    const result = formatToTimezone('2026-01-15T00:00:00');
    assertEqual(result, '1/15 08:00');
});

test('should handle UTC evening crossing to next day in Taiwan', () => {
    // UTC 20:00 Jan 14 = Taiwan 04:00 Jan 15
    const result = formatToTimezone('2026-01-14T20:00:00');
    assertEqual(result, '1/15 04:00');
});

test('should handle datetime with Z suffix', () => {
    const result = formatToTimezone('2026-01-12T05:01:04Z');
    assertEqual(result, '1/12 13:01');
});

test('should handle null input gracefully', () => {
    const result = formatToTimezone(null);
    assertEqual(result, '-');
});

test('should handle undefined input gracefully', () => {
    const result = formatToTimezone(undefined);
    assertEqual(result, '-');
});

test('should handle empty string gracefully', () => {
    const result = formatToTimezone('');
    assertEqual(result, '-');
});

test('should handle invalid date string gracefully', () => {
    const result = formatToTimezone('invalid-date');
    assertEqual(result, '-');
});

// Summary
console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);
