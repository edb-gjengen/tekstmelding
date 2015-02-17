SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8 */;

--
-- Database: `tekstmelding`
--
CREATE DATABASE IF NOT EXISTS `tekstmelding` DEFAULT CHARACTER SET utf8 COLLATE utf8_general_ci;
USE `tekstmelding`;

-- --------------------------------------------------------

--
-- Table structure for table `dlr`
--

CREATE TABLE IF NOT EXISTS `dlr` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `timestamp` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'When this row was added',
  `msgid` text COMMENT 'Sendega unique message id',
  `extID` text COMMENT 'Transparent ID reference included when sending message',
  `msisdn` double DEFAULT NULL COMMENT 'The subscribers MSISDN starting with country code',
  `errorcode` int(11) DEFAULT NULL COMMENT 'Short error code from operator, ref. sendega error code table',
  `errormessage` text COMMENT 'Long error description if error',
  `status` int(11) DEFAULT NULL COMMENT '4 = Delivered, 5 = Failed',
  `statustext` text COMMENT 'Either "delivered" or "failed"',
  `operatorerrorcode` text COMMENT 'Actual error code received from operator/network',
  `registered` text COMMENT 'Date and time when message delivered to Sendega',
  `sent` text COMMENT 'Date and time when delivered to operator/ network',
  `delivered` text COMMENT 'Date and time when message was delivered to handset',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 AUTO_INCREMENT=1 ;

-- --------------------------------------------------------

--
-- Table structure for table `event`
--

CREATE TABLE IF NOT EXISTS `event` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `timestamp` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'When this row was added',
  `incoming_id` int(11) DEFAULT NULL COMMENT 'Incoming SMS ID',
  `outgoing_id` int(11) DEFAULT NULL COMMENT 'Outgoing SMS ID',
  `dlr_id` int(11) DEFAULT NULL COMMENT 'DLR ID',
  `action` text COMMENT 'oh my god what have we done',
  `user_id` int(11) DEFAULT NULL COMMENT 'Inside user ID',
  `activation_code` text COMMENT 'Secret membership activation code',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB  DEFAULT CHARSET=utf8 AUTO_INCREMENT=1 ;

-- --------------------------------------------------------

--
-- Table structure for table `incoming`
--

CREATE TABLE IF NOT EXISTS `incoming` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `timestamp` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'When this row was added',
  `msgid` text COMMENT 'Sendega unique message id',
  `msisdn` double DEFAULT NULL COMMENT 'Subscribers MSISDN starting with country code',
  `msg` text COMMENT 'Message content',
  `mms` tinyint(1) DEFAULT NULL COMMENT 'Set to true if the message is MMS',
  `mmsdata` text COMMENT 'Contains Base64 encoded string of mms content as a zip file',
  `shortcode` int(11) DEFAULT NULL COMMENT 'The short code the message was sent to',
  `mcc` int(11) DEFAULT NULL COMMENT 'Mobile country code',
  `mnc` int(11) DEFAULT NULL COMMENT 'Mobile network code',
  `pricegroup` int(11) DEFAULT NULL COMMENT 'Tariff used for MO content',
  `keyword` text COMMENT 'The keyword used',
  `keywordid` int(11) DEFAULT NULL COMMENT 'Sendega keyword id',
  `errorcode` int(11) DEFAULT NULL COMMENT 'Used when receiving premium MO messages',
  `errormessage` text COMMENT 'Used when receiving premium MO messages',
  `registered` int(11) DEFAULT NULL COMMENT 'Date when Sendega received MO msg.',
  `ip` text COMMENT 'Request came from this IP',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB  DEFAULT CHARSET=utf8 AUTO_INCREMENT=1 ;

-- --------------------------------------------------------

--
-- Table structure for table `outgoing`
--

CREATE TABLE IF NOT EXISTS `outgoing` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `timestamp` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'When this row was added',
  `sender` text NOT NULL COMMENT 'Originating numeric or alpha numeric address for the outgoing message',
  `destination` text NOT NULL COMMENT 'MSISDN that the message should be sent to, like 47xxxxxxxx, comma separated if multiple',
  `pricegroup` int(11) NOT NULL DEFAULT '0' COMMENT 'Tariff for billing messages in ØRE',
  `contentTypeID` int(11) NOT NULL DEFAULT '1' COMMENT 'Type of message. 1 for bulk SMS, 5 for premium SMS / GAS',
  `contentHeader` text COMMENT 'Hex encoded message header for binary SMS, WAP or MMS',
  `content` text NOT NULL COMMENT 'Message content, automatically split into multiple messages if > 160',
  `dlrUrl` text COMMENT 'URL used to receive delivery reports',
  `ageLimit` int(11) NOT NULL DEFAULT '0' COMMENT 'End-user age limit for premium or adult services',
  `extID` text COMMENT 'Our local unique ID reference to an incoming SMS, returned when using DLR',
  `sendDate` text COMMENT 'Set if delivery should be delayed until this date. (YYYY-MM-DD HH:MM:SS)',
  `refID` text COMMENT 'Only used when sending premium SMS/MMS to some countries',
  `priority` int(11) NOT NULL DEFAULT '0' COMMENT '-1 = low priority, 0 = normal priority, 1 = high priority (higher rate)',
  `gwID` int(11) NOT NULL DEFAULT '0' COMMENT 'Specific gateway/supplier at Sendega',
  `pid` int(11) NOT NULL DEFAULT '0' COMMENT 'Protocol ID of message',
  `dcs` int(11) NOT NULL DEFAULT '0' COMMENT 'Data Coding Scheme',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB  DEFAULT CHARSET=utf8 AUTO_INCREMENT=1 ;
-- --------------------------------------------------------

--
-- Table structure for table `outgoing_response`
--

CREATE TABLE IF NOT EXISTS `outgoing_response` (
  `id` int(11) NOT NULL COMMENT 'Refers to a primary key in the table for outgoing messages',
  `timestamp` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'When this row was added',
  `MessageID` text NOT NULL COMMENT 'Request GUID',
  `Success` tinyint(1) NOT NULL COMMENT 'Request successful?',
  `ErrorNumber` int(11) NOT NULL DEFAULT '0' COMMENT 'Error code',
  `ErrorMessage` text COMMENT 'Error description',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
