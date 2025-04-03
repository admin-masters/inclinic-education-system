<?php
ob_start();
session_start();

define('SITEURL', 'https://services.cpdinclinic.co.in/');

define('LOCALHOST', 'localhost');

define('DB_USERNAME', 'root');

define('DB_PASSWORD', '7NVP4MvUXdbVJNYQ9UEy');

define('DB_NAME', 'reports');


$services = "services";
$message = "message";
$inditech = "cpdinclinic.co.in";
$forms = "forms";
$cpd = "cpdinclinic.co.in";
$wa = "wa.me";
$test = "testing";
$cicstage = "services";
$formstage = "forms";
$brands = "brands";
$reports = "reports";
$captcha_key = "6Le5fe4nAAAAAG61E-T-__0ewohX4z1RhJYsL_O8";

$conn = mysqli_connect(LOCALHOST, DB_USERNAME, DB_PASSWORD, DB_NAME) or die(mysqli_error($conn));
$db_select = mysqli_select_db($conn, DB_NAME) or die(mysqli_error($conn));
