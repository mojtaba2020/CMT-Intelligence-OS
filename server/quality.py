"""Non-normative pre-submission data-quality checks for CMT records.

This is not ASTM/AASHTO method execution, acceptance, or PE certification.
Do not change an engineering judgment based on these checks without an
independent qualified review of project-specific and licensed requirements.
"""
from __future__ import annotations
import math
from typing import Any

PROFILE_VERSION = 'qa-v1.1'


def audit_quality(test_type: str, record: dict[str, Any]) -> dict:
    m = record.get('measurements')
    issues = []
    calculations = {}

    def result():
        blockers=sum(i['severity']=='blocker' for i in issues)
        warnings=sum(i['severity']=='warning' for i in issues)
        return {'profile':PROFILE_VERSION,'test_type':test_type,'blockers':blockers,'warnings':warnings,
                'can_submit':blockers==0, 'items':issues, 'derived_illustrations':calculations,
                'disclaimer':'DATA QUALITY ONLY. No ASTM/AASHTO compliance, material acceptance, or professional certification.'}

    def add(severity: str, field: str, code: str, message: str):
        issues.append({'severity': severity, 'field': field, 'code': code, 'message': message})

    def value(field: str):
        x = m.get(field) if isinstance(m, dict) else None
        if isinstance(x, bool):
            add('blocker',field,'INVALID_BOOLEAN','Boolean is not a numeric measurement.')
            return None
        if x is None or x == '':
            return None
        try:
            v=float(x)
            if not math.isfinite(v):raise ValueError()
            return v
        except (ValueError,TypeError,OverflowError):
            add('blocker',field,'NOT_NUMERIC',f'{field} must be a finite numeric measurement.')
            return None

    def bounded(field: str, *, positive=False, nonnegative=False, low=None, high=None):
        v=value(field)
        if v is None:return None
        if (positive and v<=0) or (nonnegative and v<0):
            add('blocker',field,'OUT_OF_DOMAIN',f'{field} has an impossible sign for this simple calculation.')
        if low is not None and v<low:
            add('blocker',field,'OUT_OF_DOMAIN',f'{field} is below the mathematical minimum of {low}.')
        if high is not None and v>high:
            add('blocker',field,'OUT_OF_DOMAIN',f'{field} is above the mathematical maximum of {high}.')
        return v

    if not record.get('spec_reference', '').strip():
        add('blocker','spec_reference','MISSING_PROVENANCE','Missing project specification/revision reference.')
    if not record.get('evidence_reference', '').strip():
        add('blocker','evidence_reference','MISSING_PROVENANCE','Missing original measurement/evidence reference.')
    if record.get('source') not in ('synthetic','authorized'):
        add('blocker','source','UNKNOWN_SOURCE','Dataset origin must be explicitly marked.')
    if not isinstance(m,dict) or not m:
        add('blocker','measurements','NO_MEASUREMENTS','Measurements are required.')
        return result()

    # Basic math and data-integrity gates only; never method compliance or acceptance.
    # All supported workflows fail closed on missing essential measurements.
    expected = {
        'soil': ('wet','moisture','mdd'),
        'concrete': ('slump','air','temperature'),
        'soil_moisture': ('massWet','massDry','tare'),
        'atterberg': ('ll','pl'),
        'proctor': ('maxDry','optMoist','proctorMethod'),
        'sand_cone': ('excavatedMass','holeVolume','sandMoist','refMdd'),
        'sieve': ('sampleMass','retainedMass'),
        'cylinder': ('breakLoad','diameter','age'),
        'unit_weight': ('fullMass','emptyMass','calVolume'),
        'asphalt_core': ('dryCore','ssdCore','underCore','gmmCore'),
        'asphalt_voids': ('gmb','gmm'),
        'rebar_cover': ('cover','coverMin'),
        'proctor_curve': ('points',),
        'sieve_stack': ('sampleMass','points'),
        'cylinder_set': ('points',),
    }
    if test_type not in expected:
        add('blocker','test_type','NO_QA_PROFILE','No minimum data-integrity validation is implemented for this workflow.')
        return result()
    missing=[k for k in expected[test_type] if k not in m or m[k] is None or m[k]=='']
    if missing:
        add('blocker','measurements','INCOMPLETE_PROFILE',
            'Missing required fields '+', '.join(missing)+'. Correct the source mapping before submission.')
    # A complete field list is NOT evidence that sample preparation, instrument,
    # calibration, test procedure, technician competence or reporting rules were checked.
    
    if test_type=='soil':
        wet=bounded('wet',positive=True) if 'wet' in m else None
        moisture=bounded('moisture',nonnegative=True) if 'moisture' in m else None
        mdd=bounded('mdd',positive=True) if 'mdd' in m else None
        target=bounded('minComp',low=0,high=100) if 'minComp' in m else None
        if wet is not None and wet>0 and moisture is not None and moisture>=0:
            dry=wet/(1+moisture/100)
            calculations['estimated_dry_density_pcf']=round(dry,4)
            if mdd is not None and mdd>0:
                ratio=100*dry/mdd
                calculations['illustrative_compaction_pct']=round(ratio,4)
                if target is not None and 0<=target<=100 and ratio<target:
                    add('warning','minComp','BELOW_USER_THRESHOLD',
                        'Computed illustrative compaction is below a user-supplied threshold; method/rounding and specification require engineering review.')
                if ratio>120:
                    add('warning','mdd','HIGH_COMPACTION_RATIO','Computed ratio >120%; check unit consistency and Proctor reference.')
        if 'wet' in m and 'density_unit' not in m:
            add('warning','density_unit','UNDECLARED_UNIT','Assumed wet density pcf for illustrative calculation; verify instrument units.')
        if 'density_unit' in m and m['density_unit'] not in ('pcf','kg/m3'):
            add('blocker','density_unit','UNKNOWN_UNIT','Density unit must be pcf or kg/m3 for this profile.')
        if 'mdd_unit' in m and m.get('density_unit')!=m.get('mdd_unit'):
            add('blocker','mdd_unit','MIXED_UNITS','Field density and Proctor MDD units differ or are not declared consistently.')
        if m.get('density_unit')=='kg/m3' and 'estimated_dry_density_pcf' in calculations:
            calculations['estimated_dry_density_kg_m3']=calculations.pop('estimated_dry_density_pcf')

    elif test_type=='concrete':
        for field in ('slump','air','temperature'):
            if field in m:
                if field=='air':bounded(field,low=0,high=100)
                elif field=='slump':bounded(field,nonnegative=True)
                else:value(field)
        for field,base,lo,hi in (('slump','slump','slump_min','slump_max'),('air','air','air_min','air_max')):
            if lo in m and hi in m:
                mn=value(lo);mx=value(hi)
                if mn is not None and mx is not None and mn>mx:
                    add('blocker',lo,'INVERTED_LIMITS',f'{lo} cannot be greater than {hi}.')
                v=value(base) if base in m else None
                if all(x is not None for x in (v,mn,mx)) and mn<=mx and not mn<=v<=mx:
                    add('warning',base,'OUTSIDE_USER_RANGE','Measured value is outside user-entered limits; do not infer official acceptance.')

    elif test_type=='proctor':
        md=bounded('maxDry',positive=True) if 'maxDry' in m else None
        om=bounded('optMoist',low=0,high=100) if 'optMoist' in m else None
        method=m.get('proctorMethod')
        if method is not None and (not isinstance(method,str) or method not in ('Standard (D698)','Modified (D1557)','D698','D1557')):
            add('blocker','proctorMethod','UNVERIFIED_EFFORT','Use an explicitly labeled standard/modified effort; check original report.')
        if md is not None and om is not None and md>0:
            calculations['entered_reference_mdd_pcf']=round(md,4)
            calculations['entered_reference_omc_pct']=round(om,4)
            add('warning','maxDry','REFERENCE_ONLY','Values transcribed from an alleged approved report; this engine cannot verify the source or compaction method.')

    elif test_type=='sand_cone':
        wet=bounded('excavatedMass',positive=True) if 'excavatedMass' in m else None
        vol=bounded('holeVolume',positive=True) if 'holeVolume' in m else None
        moist=bounded('sandMoist',low=0,high=100) if 'sandMoist' in m else None
        ref=bounded('refMdd',positive=True) if 'refMdd' in m else None
        target=bounded('sandMinComp',low=0,high=100) if 'sandMinComp' in m else None
        if wet is not None and vol is not None and moist is not None and wet>0 and vol>0 and moist>=0:
            dry=(wet/vol)/(1+moist/100)
            calculations['illustrative_dry_density_pcf']=round(dry,4)
            if ref is not None and ref>0:
                ratio=100*dry/ref
                calculations['illustrative_compaction_pct']=round(ratio,4)
                if target is not None and ratio<target:
                    add('warning','sandMinComp','BELOW_USER_THRESHOLD','Calculated value below entered project threshold; human review required.')
        add('warning','holeVolume','INSTRUMENT_NOT_VALIDATED','Excavation/cone correction, sand calibration and moisture determination were not independently verified.')

    elif test_type=='unit_weight':
        full=bounded('fullMass',positive=True) if 'fullMass' in m else None
        empty=bounded('emptyMass',nonnegative=True) if 'emptyMass' in m else None
        vol=bounded('calVolume',positive=True) if 'calVolume' in m else None
        if all(x is not None for x in (full,empty,vol)):
            if full<=empty: add('blocker','fullMass','INVALID_MASS_ORDER','Filled mass must exceed empty container mass.')
            elif vol>0:
                density=(full-empty)/vol
                calculations['illustrative_fresh_unit_weight_pcf']=round(density,4)
                lo=value('uwMin') if 'uwMin' in m else None
                hi=value('uwMax') if 'uwMax' in m else None
                if lo is not None and hi is not None and lo>hi:add('blocker','uwMin','INVERTED_LIMITS','Minimum exceeds maximum.')
                if lo is not None and density<lo or hi is not None and density>hi:
                    add('warning','fullMass','OUTSIDE_USER_RANGE','Outside entered project range; not a formal acceptance decision.')
        add('warning','calVolume','CALIBRATION_NOT_CHECKED','Calibration of measure and procedures not independently verified.')

    elif test_type=='asphalt_core':
        dry=bounded('dryCore',positive=True) if 'dryCore' in m else None
        ssd=bounded('ssdCore',positive=True) if 'ssdCore' in m else None
        submerged=bounded('underCore',nonnegative=True) if 'underCore' in m else None
        gmm=bounded('gmmCore',positive=True) if 'gmmCore' in m else None
        if all(x is not None for x in (dry,ssd,submerged)):
            if not ssd>=dry or not ssd>submerged:
                add('blocker','ssdCore','INVALID_MASS_ORDER','Expected SSD >= dry and SSD > immersed mass.')
            elif ssd>submerged:
                gmb=dry/(ssd-submerged)
                calculations['illustrative_bulk_sg']=round(gmb,5)
                if gmm is not None and gmm>0:
                    ratio=100*gmb/gmm
                    calculations['illustrative_pct_gmm']=round(ratio,4)
                    if ratio>100:
                        add('blocker','gmmCore','DENSITY_RELATION','Calculated Gmb exceeds supplied Gmm; verify source, units and method.')
                    low=value('rcMin') if 'rcMin' in m else None
                    high=value('rcMax') if 'rcMax' in m else None
                    if low is not None and high is not None and low>high: add('blocker','rcMin','INVERTED_LIMITS','Minimum exceeds maximum.')
                    if low is not None and ratio<low or high is not None and ratio>high:
                        add('warning','gmmCore','OUTSIDE_USER_RANGE','Calculated %Gmm outside entered project limits.')
        add('warning','dryCore','METHOD_APPLICABILITY_UNVERIFIED','Absorption/method suitability and corrections have not been verified.')

    elif test_type=='asphalt_voids':
        gmb=bounded('gmb',positive=True) if 'gmb' in m else None
        gmm=bounded('gmm',positive=True) if 'gmm' in m else None
        if gmb is not None and gmm is not None and gmm>0:
            if gmb>gmm:
                add('blocker','gmb','DENSITY_RELATION','Bulk SG must not exceed theoretical maximum SG for this simple calculation.')
            else:
                air=100*(1-gmb/gmm)
                calculations['illustrative_air_voids_pct']=round(air,4)
                low=value('voidMin') if 'voidMin' in m else None
                high=value('voidMax') if 'voidMax' in m else None
                if low is not None and high is not None and low>high: add('blocker','voidMin','INVERTED_LIMITS','Minimum exceeds maximum.')
                if low is not None and air<low or high is not None and air>high:
                    add('warning','gmb','OUTSIDE_USER_RANGE','Outside user-entered project range.')
        add('warning','gmm','SOURCE_GRAVITIES_UNVERIFIED','Entered Gmb and Gmm methods/corrections were not validated.')

    elif test_type=='rebar_cover':
        cover=bounded('cover',nonnegative=True) if 'cover' in m else None
        low=bounded('coverMin',nonnegative=True) if 'coverMin' in m else None
        high=bounded('coverMax',nonnegative=True) if 'coverMax' in m else None
        if low is not None and high is not None and low>high:
            add('blocker','coverMin','INVERTED_LIMITS','Specified minimum is above specified maximum.')
        if cover is not None and (low is not None and cover<low or high is not None and cover>high):
            add('warning','cover','OUTSIDE_USER_RANGE','Cover outside entered drawing limits; field verification and engineering review required.')
        add('warning','cover','DRAWING_UNVERIFIED','Approved drawing revision and applicable tolerances have not been independently checked.')

    elif test_type=='soil_moisture':
        keys=('massWet','massDry','tare')
        if all(k in m for k in keys):
            wet=bounded('massWet',positive=True);dry=bounded('massDry',positive=True);tare=bounded('tare',nonnegative=True)
            if all(v is not None for v in (wet,dry,tare)):
                if not wet>=dry>tare:
                    add('blocker','massDry','INVALID_MASS_ORDER','Require wet mass >= dry mass > tare mass.')
                else:
                    calculations['water_content_pct']=round(100*(wet-dry)/(dry-tare),4)

    elif test_type=='atterberg':
        if 'll' in m and 'pl' in m:
            ll=bounded('ll',nonnegative=True);pl=bounded('pl',nonnegative=True)
            if ll is not None and pl is not None:
                if ll<pl:add('blocker','ll','INVALID_LIMIT_ORDER','Liquid limit must not be below plastic limit for this arithmetic profile.')
                else:calculations['plasticity_index']=round(ll-pl,4)

    elif test_type=='sieve':
        if 'sampleMass' in m and 'retainedMass' in m:
            sample=bounded('sampleMass',positive=True);ret=bounded('retainedMass',nonnegative=True)
            if sample is not None and ret is not None and sample>0:
                if ret>sample:add('blocker','retainedMass','MASS_OVER_SAMPLE','Retained mass exceeds sample mass.')
                else:calculations['percent_passing']=round(100*(1-ret/sample),4)

    elif test_type=='cylinder':
        if all(k in m for k in ('breakLoad','diameter')):
            load=bounded('breakLoad',positive=True);dia=bounded('diameter',positive=True)
            if load is not None and dia is not None and load>0 and dia>0:
                calculations['illustrative_strength_psi']=round(4*load/(math.pi*dia*dia),4)
        if 'age' in m:bounded('age',nonnegative=True)

    elif test_type=='sieve_stack':
        if 'sampleMass' in m and 'points' in m:
            sample=bounded('sampleMass',positive=True);points=m['points']
            if not isinstance(points,list) or not points:
                add('blocker','points','MISSING_ROWS','Sieve stack must contain rows.')
            else:
                total=0;last=float('inf');used=set();valid=True
                for i,p in enumerate(points):
                    if not isinstance(p,dict):
                        add('blocker',f'points[{i}]','INVALID_ROW','Sieve row is not an object.');valid=False;continue
                    try:
                        mm=float(p['mm']); mass=float(p['mass'])
                        if not math.isfinite(mm) or not math.isfinite(mass):raise ValueError()
                    except (ValueError,TypeError,KeyError,OverflowError):
                        add('blocker',f'points[{i}]','INVALID_ROW','A sieve row needs numeric mm and mass.');valid=False;continue
                    if mm<0 or mass<0 or mm>=last or mm in used:
                        add('blocker',f'points[{i}]','INVALID_SIEVE_ORDER','Openings must strictly decrease; masses must be nonnegative.');valid=False
                    last=mm;used.add(mm);total+=mass
                if valid and sample is not None and sample>0:
                    diff=100*(total-sample)/sample
                    calculations['mass_balance_difference_pct']=round(diff,4)
                    tol=m.get('balanceTol')
                    if tol is None:
                        add('warning','balanceTol','NO_TOLERANCE','Project/lab-selected mass balance review tolerance is not entered.')
                    else:
                        t=bounded('balanceTol',nonnegative=True)
                        if t is not None and abs(diff)>t:
                            add('warning','points','MASS_BALANCE_DIFFERENCE','Mass balance exceeds user-entered review tolerance.')

    elif test_type=='proctor_curve':
        pts=m.get('points')
        if isinstance(pts,list) and len(pts)>=3:
            out=[];valid=True;seen=set()
            for i,p in enumerate(pts):
                try:
                    w=float(p['wet']);moist=float(p['moisture'])
                    if not math.isfinite(w) or not math.isfinite(moist) or w<=0 or moist<0 or moist in seen:raise ValueError()
                    out.append((moist,w/(1+moist/100)));seen.add(moist)
                except (ValueError,TypeError,KeyError,OverflowError):
                    add('blocker',f'points[{i}]','INVALID_POINT','Each point requires distinct nonnegative moisture and positive wet density.');valid=False
            if valid:
                best=max(out,key=lambda x:x[1]);calculations['observed_peak_moisture_pct']=round(best[0],4)
                calculations['observed_peak_dry_density_pcf']=round(best[1],4)
                if best[0] in (min(x[0] for x in out),max(x[0] for x in out)):
                    add('warning','points','BOUNDARY_PEAK','Measured maximum at curve boundary; review adequacy of laboratory points.')
        elif pts is not None:
            add('blocker','points','TOO_FEW_POINTS','Three or more data points are required by this illustration profile.')

    elif test_type=='cylinder_set':
        pts=m.get('points')
        if isinstance(pts,list) and pts:
            ages=set(); strengths=[]
            for i,p in enumerate(pts):
                try:
                    age=float(p['age']);dia=float(p['diameter']);load=float(p['load'])
                    if not all(math.isfinite(x) for x in (age,dia,load)) or age<0 or dia<=0 or load<=0:raise ValueError()
                    ages.add(age);strengths.append(4*load/(math.pi*dia**2))
                except (KeyError,ValueError,TypeError,OverflowError):
                    add('blocker',f'points[{i}]','INVALID_CYLINDER','Cylinder needs age >=0, diameter >0 and load >0.')
            if len(ages)>1:
                add('warning','points','MIXED_AGES','Mixed test ages: do not compute a single set mean.')
            elif len(strengths)==len(pts):
                calculations['illustrative_set_mean_psi']=round(sum(strengths)/len(strengths),4)
        elif pts is not None:
            add('blocker','points','MISSING_ROWS','Cylinder set requires cylinder rows.')

    # No jurisdiction/project acceptance determination is made by this engine.
    return result()

