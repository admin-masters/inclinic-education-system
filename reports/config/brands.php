<?php
ob_start();
session_start();

$servername = '13.234.88.80';
$username = 'test_doctor_u';
$password = 'V.D@-6*CwL0dmMP0';
$dbname = 'test_doctor';

// Create connection

$conn = new mysqli($servername, $username, $password, $dbname);

// Check connection

if ($conn->connect_error) {

    die('Connection failed: ' . $conn->connect_error);
}

$cpd = 'cpdinclinic.co.in';
$user = 'user2';
$inditech = 'testing.inditech.co.in';
$cicstage = "services";
$formstage = "forms";
$brands = "brandsnewstage";
$reports = "reports";
$captcha_key = "6Le5fe4nAAAAAG61E-T-__0ewohX4z1RhJYsL_O8";
