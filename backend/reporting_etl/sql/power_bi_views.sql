-- View: total PDF impressions per campaign
CREATE OR REPLACE VIEW vw_pdf_impressions AS
SELECT c.id            AS campaign_id,
       c.name          AS campaign_name,
       COUNT(DISTINCT de.id) AS pdf_impressions
FROM campaign_management_campaign        AS c
JOIN sharing_management_sharelog         AS sl  ON sl.doctor_identifier IS NOT NULL
JOIN doctor_viewer_doctorengagement      AS de  ON de.short_link_id = sl.short_link_id
WHERE de.pdf_completed = 1
GROUP BY c.id, c.name;

-- View: video completions (90 %+)
CREATE OR REPLACE VIEW vw_video_completions AS
SELECT c.id, c.name,
       COUNT(DISTINCT de.id) AS video_completions
FROM campaign_management_campaign        AS c
JOIN sharing_management_sharelog         AS sl  ON sl.doctor_identifier IS NOT NULL
JOIN doctor_viewer_doctorengagement      AS de  ON de.short_link_id = sl.short_link_id
WHERE de.video_watch_percentage >= 90
GROUP BY c.id, c.name;