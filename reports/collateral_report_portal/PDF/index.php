<?php
ini_set('memory_limit', '512M');
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
error_reporting(E_ALL);

// Fetching parameters from the URL
$start_date = isset($_GET['start_date']) ? $_GET['start_date'] : null;
$end_date = isset($_GET['end_date']) ? $_GET['end_date'] : null;
$brand_campaign_id = isset($_GET['brand_campaign_id']) ? $_GET['brand_campaign_id'] : null;

require 'vendor/autoload.php'; // Path to Composer autoload.php
require '../../vendor/tecnickcom/tcpdf/tcpdf.php'; // Path to FPDI autoload.php
include '../../config/constants.php';

use Dompdf\Dompdf;
use setasign\Fpdi\Tcpdf\Fpdi; // Use the TCPDF FPDI integration
use TCPDF;

function fetchHtmlContent($url) {
    $contextOptions = [
        "ssl" => [
            "verify_peer" => false,
            "verify_peer_name" => false,
        ],
    ];
    $context = stream_context_create($contextOptions);
    $html = @file_get_contents($url, false, $context); // Suppress warnings and handle manually
    if ($html === FALSE) {
        die('Error fetching HTML content from URL: ' . error_get_last()['message']);
    }
    return $html;
}

function removeUnwantedElements($html) {
    $dom = new DOMDocument();
    libxml_use_internal_errors(true); // Suppress warnings due to malformed HTML
    $dom->loadHTML($html);
    libxml_clear_errors();

    // Remove specific buttons and anchor tags
    $tagsToRemove = ['button', 'a']; // Tags to be removed

    foreach ($tagsToRemove as $tag) {
        $elements = $dom->getElementsByTagName($tag);
        while ($elements->length > 0) {
            $elements->item(0)->parentNode->removeChild($elements->item(0));
        }
    }

    // Convert back to HTML
    $cleanedHtml = $dom->saveHTML();
    return $cleanedHtml;
}

function generatePDF($html) {
    // Initialize DOMPDF
    $dompdf = new Dompdf();
    
    // Add custom styles for better formatting
    $customCSS = '
        <style>
            body {
                font-family: Arial, sans-serif;
                font-size: 12px;
                margin: 10px;
            }
            table {
                width: 100%;
                border-collapse: collapse;
            }
            th, td {
                border: 1px solid #ddd;
                padding: 8px;
                text-align: left;
            }
            th {
                background-color: #f2f2f2;
                font-weight: bold;
            }
            .page-break {
                page-break-before: always;
            }
        </style>
    ';

    // Combine HTML content with custom CSS
    $html = $customCSS . $html;

    $dompdf->loadHtml($html);

    // Set paper size and orientation to portrait
    $dompdf->setPaper('A4', 'portrait');

    // Render the HTML as PDF
    $dompdf->render();

    // Output the generated PDF to the browser
    $dompdf->stream("report.pdf", ["Attachment" => 1]); // Attachment 1 means it will prompt for download
}


// Validate required parameters
if (!$brand_campaign_id) {
    die('Invalid or missing brand_campaign_id.');
}

// Construct URL based on the parameters
$url = "https://$reports.$cpd/reports/collateral_report_portal/{$brand_campaign_id}/index.php?start_date={$start_date}&end_date={$end_date}&brand_campaign_id={$brand_campaign_id}";

// Log the URL to debug
error_log("Fetching URL: " . $url);

// Fetch HTML content
$htmlContent = fetchHtmlContent($url);
if (!$htmlContent) {
    die('No content fetched from the URL. Please check the URL or data source.');
}

// Remove unwanted elements, including specific buttons and anchor tags
$cleanedHtmlContent = removeUnwantedElements($htmlContent);

// Generate the PDF from the cleaned HTML content
generatePDF($cleanedHtmlContent);
?>
