SELECT customer_id, SUM(amount) OVER (PARTITION BY customer_id) FROM invoices;
