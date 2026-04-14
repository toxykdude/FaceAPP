/**
 * Member form for create/edit operations.
 */
import React from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
    Box,
    Button,
    Card,
    CardContent,
    TextField,
    Typography,
    Grid,
    FormControlLabel,
    Checkbox,
    MenuItem,
    Alert,
    Paper,
    Chip,
    InputAdornment,
    CircularProgress,
} from '@mui/material';
import { PhotoCamera } from '@mui/icons-material';
import { membersApi, MemberCreate, MemberUpdate } from '@/api/members';
import { membershipsApi } from '@/api/memberships';
import { membershipPlansApi, MembershipPlan } from '@/api/membershipPlans';
import { salesApi } from '@/api/sales';
import { addDays, format } from 'date-fns';

const memberSchema = z.object({
    first_name: z.string().min(1, 'First name is required'),
    last_name: z.string().min(1, 'Last name is required'),
    email: z.string().optional().transform(v => v === '' ? undefined : v).pipe(z.string().email('Invalid email address').optional()),
    phone: z.string().optional(),
    id_number: z.string().optional(),
    date_of_birth: z.string().optional(),
    address: z.string().optional(),
    consent_given: z.boolean(),
    status: z.enum(['active', 'inactive', 'suspended']).optional(),
});

type MemberFormData = z.infer<typeof memberSchema>;

export const MemberForm: React.FC = () => {
    const navigate = useNavigate();
    const { id } = useParams();
    const queryClient = useQueryClient();
    const isEdit = !!id;
    const [createdMemberId, setCreatedMemberId] = React.useState<string | null>(null);

    const { data: member } = useQuery({
        queryKey: ['member', id],
        queryFn: () => membersApi.getMember(id!),
        enabled: isEdit,
    });

    const {
        control,
        handleSubmit,
        formState: { errors },
    } = useForm<MemberFormData>({
        resolver: zodResolver(memberSchema),
        defaultValues: member || {
            first_name: '',
            last_name: '',
            email: '',
            phone: '',
            id_number: '',
            consent_given: false,
            status: 'active',
        },
    });

    const createMutation = useMutation({
        mutationFn: (data: MemberCreate) => membersApi.createMember(data),
        onSuccess: (data) => {
            queryClient.invalidateQueries({ queryKey: ['members'] });
            setCreatedMemberId(data.id);
        },
        onError: (error: any) => {
            const detail = error?.response?.data?.detail || error?.message || 'Failed to create member';
            alert('Error creating member: ' + detail);
        },
    });

    const updateMutation = useMutation({
        mutationFn: (data: MemberUpdate) => membersApi.updateMember(id!, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['members'] });
            queryClient.invalidateQueries({ queryKey: ['member', id] });
            navigate('/members');
        },
    });

    // The effective member ID for sub-components
    const effectiveMemberId = id || createdMemberId;
    const showSubSections = isEdit || !!createdMemberId;

    const onSubmit = (data: MemberFormData) => {
        if (isEdit) {
            updateMutation.mutate(data);
        } else {
            createMutation.mutate(data as MemberCreate);
        }
    };

    return (
        <Box>
            <Typography variant="h4" gutterBottom>
                {isEdit ? 'Edit Member' : 'Add Member'}
            </Typography>

            {/* Only show form if member hasn't been created yet */}
            {(!createdMemberId && !isEdit) && (
            <Card>
                <CardContent>
                    <form onSubmit={handleSubmit(onSubmit)}>
                        <Grid container spacing={3}>
                            <Grid item xs={12} sm={6}>
                                <Controller
                                    name="first_name"
                                    control={control}
                                    render={({ field }) => (
                                        <TextField
                                            {...field}
                                            fullWidth
                                            label="First Name"
                                            error={!!errors.first_name}
                                            helperText={errors.first_name?.message}
                                        />
                                    )}
                                />
                            </Grid>

                            <Grid item xs={12} sm={6}>
                                <Controller
                                    name="last_name"
                                    control={control}
                                    render={({ field }) => (
                                        <TextField
                                            {...field}
                                            fullWidth
                                            label="Last Name"
                                            error={!!errors.last_name}
                                            helperText={errors.last_name?.message}
                                        />
                                    )}
                                />
                            </Grid>

                            <Grid item xs={12} sm={6}>
                                <Controller
                                    name="id_number"
                                    control={control}
                                    render={({ field }) => (
                                        <TextField
                                            {...field}
                                            fullWidth
                                            label="Cedula / ID Number"
                                            placeholder="e.g. 12345678"
                                        />
                                    )}
                                />
                            </Grid>

                            <Grid item xs={12} sm={6}>
                                <Controller
                                    name="email"
                                    control={control}
                                    render={({ field }) => (
                                        <TextField
                                            {...field}
                                            fullWidth
                                            label="Email (optional)"
                                            placeholder="email@example.com"
                                            error={!!errors.email}
                                            helperText={errors.email?.message}
                                        />
                                    )}
                                />
                            </Grid>

                            <Grid item xs={12} sm={6}>
                                <Controller
                                    name="phone"
                                    control={control}
                                    render={({ field }) => (
                                        <TextField
                                            {...field}
                                            fullWidth
                                            label="Phone"
                                            error={!!errors.phone}
                                            helperText={errors.phone?.message}
                                        />
                                    )}
                                />
                            </Grid>

                            <Grid item xs={12} sm={6}>
                                <Controller
                                    name="date_of_birth"
                                    control={control}
                                    render={({ field }) => (
                                        <TextField
                                            {...field}
                                            fullWidth
                                            label="Date of Birth"
                                            type="date"
                                            InputLabelProps={{ shrink: true }}
                                        />
                                    )}
                                />
                            </Grid>

                            {isEdit && (
                                <Grid item xs={12} sm={6}>
                                    <Controller
                                        name="status"
                                        control={control}
                                        render={({ field }) => (
                                            <TextField {...field} fullWidth select label="Status">
                                                <MenuItem value="active">Active</MenuItem>
                                                <MenuItem value="inactive">Inactive</MenuItem>
                                                <MenuItem value="suspended">Suspended</MenuItem>
                                            </TextField>
                                        )}
                                    />
                                </Grid>
                            )}

                            <Grid item xs={12}>
                                <Controller
                                    name="address"
                                    control={control}
                                    render={({ field }) => (
                                        <TextField {...field} fullWidth label="Address" multiline rows={2} />
                                    )}
                                />
                            </Grid>

                            <Grid item xs={12}>
                                <Controller
                                    name="consent_given"
                                    control={control}
                                    render={({ field }) => (
                                        <FormControlLabel
                                            control={<Checkbox {...field} checked={field.value} />}
                                            label="Consent given for biometric data collection"
                                        />
                                    )}
                                />
                            </Grid>

                            <Grid item xs={12}>
                                <Box display="flex" gap={2}>
                                    <Button type="submit" variant="contained" size="large">
                                        {isEdit ? 'Update' : 'Create'}
                                    </Button>
                                    <Button
                                        variant="outlined"
                                        size="large"
                                        onClick={() => navigate('/members')}
                                    >
                                        Cancel
                                    </Button>
                                </Box>
                            </Grid>
                        </Grid>
                    </form>
                </CardContent>
            </Card>
            )}

            {/* Success message after creation */}
            {createdMemberId && !isEdit && (
                <Paper sx={{ p: 3, mb: 3, bgcolor: 'success.lighter', borderRadius: 2 }}>
                    <Typography variant="h6" color="success.main">✅ Member created successfully!</Typography>
                    <Typography variant="body2" color="textSecondary">
                        Now you can assign a membership and enroll their face below.
                    </Typography>
                    <Button sx={{ mt: 1 }} onClick={() => navigate('/members')}>Skip - Go to Members List</Button>
                </Paper>
            )}

            {/* Membership Section - shown after creation or in edit mode */}
            {showSubSections && effectiveMemberId && <MembershipSection memberId={effectiveMemberId} />}

            {/* Face Enrollment Section - shown after creation or in edit mode */}
            {showSubSections && effectiveMemberId && <FaceEnrollmentSection memberId={effectiveMemberId} />}
        </Box>
    );
};

// Sub-component for Membership Section - inline, no dialog
interface MembershipHistoryItem {
    id: string;
    member_id: string;
    plan_id?: string;
    type: string;
    start_date: string;
    end_date: string;
    price: number;
    status: 'active' | 'expired' | 'cancelled' | 'suspended';
    created_at: string;
    updated_at: string;
    plan_name?: string;
}

const MembershipSection: React.FC<{ memberId: string }> = ({ memberId }) => {
    const queryClient = useQueryClient();

    const [showForm, setShowForm] = React.useState(false);
    const [renewFromMembership, setRenewFromMembership] = React.useState<MembershipHistoryItem | null>(null);
    const [selectedPlanId, setSelectedPlanId] = React.useState('');
    const [startDate, setStartDate] = React.useState(format(new Date(), 'yyyy-MM-dd'));
    const [paymentMethod, setPaymentMethod] = React.useState<'cash' | 'transfer'>('cash');
    const [paymentAmount, setPaymentAmount] = React.useState<string>('');

    // Fetch existing memberships for this member
    const { data: memberships, isLoading: membershipsLoading } = useQuery({
        queryKey: ['memberships', 'member', memberId],
        queryFn: () => membershipsApi.getMemberships(0, 50, memberId),
    });

    // Sort by end_date descending (most recent first)
    const sortedMemberships = React.useMemo(() => {
        if (!memberships) return [];
        return [...memberships].sort((a, b) => new Date(b.end_date).getTime() - new Date(a.end_date).getTime());
    }, [memberships]);

    const { data: plansData } = useQuery({
        queryKey: ['membershipPlans', 'active'],
        queryFn: () => membershipPlansApi.getPlans(true)
    });
    const plans = plansData?.plans || [];

    const selectedPlan = plans.find((p: MembershipPlan) => p.id === selectedPlanId);

    // Auto-calculate end date from plan duration
    const endDate = React.useMemo(() => {
        if (!selectedPlan || !startDate) return '';
        const start = new Date(startDate);
        const end = addDays(start, selectedPlan.duration_days || 0);
        return format(end, 'yyyy-MM-dd');
    }, [selectedPlanId, startDate, selectedPlan]);

    // Auto-fill payment amount when plan changes
    React.useEffect(() => {
        if (selectedPlan) {
            setPaymentAmount(String(selectedPlan.price));
        }
    }, [selectedPlanId, selectedPlan]);

    const price = selectedPlan ? Number(selectedPlan.price) : 0;
    const paidAmount = Number(paymentAmount) || 0;
    const isPartial = paidAmount < price && paidAmount > 0;
    const isPending = paidAmount === 0;
    const isPaid = paidAmount >= price;

    const createMutation = useMutation({
        mutationFn: async (data: any) => {
            // 1. Create membership
            const membership = await membershipsApi.createMembership(data.membership);
            // 2. Create payment transaction if amount > 0
            if (data.payment.amount > 0) {
                await salesApi.createTransaction({
                    member_id: data.membership.member_id,
                    membership_id: membership.id,
                    amount: data.payment.amount,
                    payment_method: data.payment.method,
                    notes: data.payment.notes || undefined,
                });
            }
            return membership;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['memberships'] });
            queryClient.invalidateQueries({ queryKey: ['memberships', 'member', memberId] });
            setShowForm(false);
            setRenewFromMembership(null);
            setSelectedPlanId('');
            setPaymentAmount('');
            setPaymentMethod('cash');
            setStartDate(format(new Date(), 'yyyy-MM-dd'));
        },
        onError: (error: any) => {
            alert(`Error: ${error.response?.data?.detail || error.message}`);
        }
    });

    const handleAssign = () => {
        if (!selectedPlan) return;
        createMutation.mutate({
            membership: {
                member_id: memberId,
                plan_id: selectedPlanId,
                type: selectedPlan.name,
                start_date: startDate,
                end_date: endDate,
                price: price,
            },
            payment: {
                amount: paidAmount,
                method: paymentMethod,
                notes: isPartial ? `Pago parcial. Pendiente: $${price - paidAmount}` : 'Pago completo',
            }
        });
    };

    const handleRenew = (membership: MembershipHistoryItem) => {
        setRenewFromMembership(membership);
        if (membership.plan_id) {
            setSelectedPlanId(membership.plan_id);
        }
        // Start date = day after the membership ends
        const nextDay = addDays(new Date(membership.end_date), 1);
        setStartDate(format(nextDay, 'yyyy-MM-dd'));
        setPaymentMethod('cash');
        setShowForm(true);
    };

    const handleAddNew = () => {
        setRenewFromMembership(null);
        setSelectedPlanId('');
        setStartDate(format(new Date(), 'yyyy-MM-dd'));
        setPaymentAmount('');
        setPaymentMethod('cash');
        setShowForm(true);
    };

    const handleCancelForm = () => {
        setShowForm(false);
        setRenewFromMembership(null);
        setSelectedPlanId('');
        setPaymentAmount('');
        setPaymentMethod('cash');
        setStartDate(format(new Date(), 'yyyy-MM-dd'));
    };

    const formatPlanLabel = (plan: MembershipPlan) => {
        const durationParts: string[] = [];
        if (plan.duration_months) durationParts.push(`${plan.duration_months}m`);
        if (plan.duration_days) durationParts.push(`${plan.duration_days}d`);
        const durationStr = durationParts.join(' ') || '0d';
        return `${plan.name} \u2014 $${Number(plan.price).toLocaleString()} (${durationStr})`;
    };

    const formatDate = (dateStr: string) => {
        try {
            return format(new Date(dateStr), 'MMM d, yyyy');
        } catch {
            return dateStr;
        }
    };

    const getStatusChip = (status: string) => {
        switch (status) {
            case 'active':
                return <Chip label="Active" color="success" size="small" icon={<span>{'\u2705'}</span>} />;
            case 'expired':
                return <Chip label="Expired" color="error" size="small" icon={<span>{'\u26d4'}</span>} />;
            case 'cancelled':
                return <Chip label="Cancelled" color="default" size="small" icon={<span>{'\ud83d\udeab'}</span>} />;
            case 'suspended':
                return <Chip label="Suspended" color="warning" size="small" icon={<span>{'\u23f8\ufe0f'}</span>} />;
            default:
                return <Chip label={status} size="small" />;
        }
    };

    return (
        <Card sx={{ mt: 3 }}>
            <CardContent>
                <Typography variant="h6" gutterBottom>Membership History</Typography>

                {membershipsLoading && (
                    <Box display="flex" justifyContent="center" p={3}>
                        <CircularProgress size={24} />
                    </Box>
                )}

                {!showForm && !membershipsLoading && (
                    <>
                        {sortedMemberships.length === 0 ? (
                            <Typography variant="body2" color="textSecondary" sx={{ py: 2 }}>
                                No memberships found for this member.
                            </Typography>
                        ) : (
                            <Box display="flex" flexDirection="column" gap={1.5}>
                                {sortedMemberships.map((m) => (
                                    <Paper
                                        key={m.id}
                                        variant="outlined"
                                        sx={{
                                            p: 2,
                                            display: 'flex',
                                            alignItems: 'center',
                                            justifyContent: 'space-between',
                                            gap: 2,
                                        }}
                                    >
                                        <Box>
                                            <Box display="flex" alignItems="center" gap={1} mb={0.5}>
                                                <Typography variant="subtitle1" fontWeight="bold">
                                                    {m.plan_name || m.type}
                                                </Typography>
                                                {getStatusChip(m.status)}
                                            </Box>
                                            <Typography variant="body2" color="textSecondary">
                                                {formatDate(m.start_date)} {'\u2192'} {formatDate(m.end_date)}
                                            </Typography>
                                            <Typography variant="body2" fontWeight="500">
                                                ${Number(m.price).toLocaleString()}
                                            </Typography>
                                        </Box>
                                        <Button
                                            variant="outlined"
                                            size="small"
                                            color={m.status === 'active' ? 'success' : m.status === 'expired' ? 'warning' : 'primary'}
                                            onClick={() => handleRenew(m)}
                                        >
                                            Renew
                                        </Button>
                                    </Paper>
                                ))}
                            </Box>
                        )}

                        <Button
                            variant="text"
                            startIcon={<span>+</span>}
                            onClick={handleAddNew}
                            sx={{ mt: 2 }}
                        >
                            Add New Membership
                        </Button>
                    </>
                )}

                {showForm && (
                    <>
                        <Box display="flex" alignItems="center" gap={1} mb={2}>
                            <Typography variant="subtitle1" fontWeight="bold">
                                {renewFromMembership ? 'Renew Membership' : 'Assign New Membership'}
                            </Typography>
                            {renewFromMembership && getStatusChip(renewFromMembership.status)}
                        </Box>

                        {renewFromMembership && (
                            <Alert severity="info" sx={{ mb: 2 }}>
                                Renewing <strong>{renewFromMembership.plan_name || renewFromMembership.type}</strong> {'\u2014'}
                                {' '}Previous: {formatDate(renewFromMembership.start_date)} {'\u2192'} {formatDate(renewFromMembership.end_date)}
                            </Alert>
                        )}

                        <Box display="flex" flexDirection="column" gap={2}>
                            <TextField
                                select
                                label="Select Plan"
                                value={selectedPlanId}
                                onChange={(e) => setSelectedPlanId(e.target.value)}
                                fullWidth
                                required
                            >
                                <MenuItem value=""><em>Choose a plan...</em></MenuItem>
                                {plans.map((plan: MembershipPlan) => (
                                    <MenuItem key={plan.id} value={plan.id}>
                                        {formatPlanLabel(plan)}
                                    </MenuItem>
                                ))}
                            </TextField>

                            <Grid container spacing={2}>
                                <Grid item xs={6}>
                                    <TextField
                                        label="Start Date"
                                        type="date"
                                        value={startDate}
                                        onChange={(e) => setStartDate(e.target.value)}
                                        fullWidth
                                        InputLabelProps={{ shrink: true }}
                                    />
                                </Grid>
                                <Grid item xs={6}>
                                    <TextField
                                        label="End Date"
                                        type="date"
                                        value={endDate}
                                        fullWidth
                                        InputLabelProps={{ shrink: true }}
                                        InputProps={{ readOnly: true }}
                                        helperText="Auto-calculated from plan"
                                        sx={{ '& .MuiInputBase-input': { color: 'text.secondary' } }}
                                    />
                                </Grid>
                            </Grid>

                            {selectedPlan && (
                                <TextField
                                    label="Plan Price"
                                    value={`$${price.toLocaleString()}`}
                                    fullWidth
                                    InputProps={{ readOnly: true }}
                                    sx={{ '& .MuiInputBase-input': { fontWeight: 'bold', fontSize: '1.1rem' } }}
                                />
                            )}

                            {selectedPlan && (
                                <>
                                    <TextField
                                        select
                                        label="Payment Method"
                                        value={paymentMethod}
                                        onChange={(e) => setPaymentMethod(e.target.value as 'cash' | 'transfer')}
                                        fullWidth
                                    >
                                        <MenuItem value="cash">{'\ud83d\udcb5'} Efectivo (Cash)</MenuItem>
                                        <MenuItem value="transfer">{'\ud83c\udfe6'} Transferencia (Transfer)</MenuItem>
                                    </TextField>

                                    <TextField
                                        label="Payment Amount"
                                        type="number"
                                        value={paymentAmount}
                                        onChange={(e) => setPaymentAmount(e.target.value)}
                                        fullWidth
                                        InputProps={{
                                            startAdornment: <InputAdornment position="start">$</InputAdornment>,
                                        }}
                                        helperText={
                                            isPaid ? "\u2705 Pago completo" :
                                            isPartial ? `\u26a0\ufe0f Pago parcial \u2014 Falta: $${(price - paidAmount).toLocaleString()}` :
                                            "\u274c Sin pago (pendiente)"
                                        }
                                    />

                                    <Box>
                                        {isPaid && <Chip label="Pagado" color="success" />}
                                        {isPartial && <Chip label={`Parcial: $${paidAmount.toLocaleString()} de $${price.toLocaleString()}`} color="warning" />}
                                        {isPending && <Chip label="Pendiente" color="error" />}
                                    </Box>
                                </>
                            )}

                            <Box display="flex" gap={2}>
                                <Button
                                    onClick={handleAssign}
                                    variant="contained"
                                    size="large"
                                    disabled={!selectedPlanId || createMutation.isPending}
                                    fullWidth
                                >
                                    {createMutation.isPending ? "Assigning..." : "Assign Membership"}
                                </Button>
                                <Button
                                    onClick={handleCancelForm}
                                    variant="outlined"
                                    size="large"
                                    fullWidth
                                >
                                    Cancel
                                </Button>
                            </Box>
                        </Box>
                    </>
                )}
            </CardContent>
        </Card>
    );
};

// Sub-component for Face Enrollment
const FaceEnrollmentSection: React.FC<{ memberId: string }> = ({ memberId }) => {
    const [enrollmentStatus, setEnrollmentStatus] = React.useState<'idle' | 'uploading' | 'success' | 'error'>('idle');
    const [qualityScore, setQualityScore] = React.useState<number | null>(null);
    const [errorMsg, setErrorMsg] = React.useState<string>('');
    const [cameraActive, setCameraActive] = React.useState(false);
    const [stream, setStream] = React.useState<MediaStream | null>(null);
    const fileInputRef = React.useRef<HTMLInputElement>(null);
    const videoRef = React.useRef<HTMLVideoElement>(null);
    const canvasRef = React.useRef<HTMLCanvasElement>(null);

    const enrollWithFile = async (file: File) => {
        setEnrollmentStatus('uploading');
        setErrorMsg('');
        try {
            const result = await membersApi.enrollBiometric(memberId, file);
            setQualityScore(result.quality_score);
            setEnrollmentStatus('success');
        } catch (error: any) {
            const detail = error?.response?.data?.detail || error?.message || 'Unknown error';
            setErrorMsg(detail);
            setEnrollmentStatus('error');
        }
    };

    const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;
        await enrollWithFile(file);
    };

    const startCamera = async () => {
        try {
            const mediaStream = await navigator.mediaDevices.getUserMedia({
                video: { width: 640, height: 480, facingMode: 'user' }
            });
            setStream(mediaStream);
            setCameraActive(true);
            setErrorMsg('');
            // Attach stream to video element after render
            setTimeout(() => {
                if (videoRef.current) {
                    videoRef.current.srcObject = mediaStream;
                }
            }, 100);
        } catch (err: any) {
            setErrorMsg('Could not access camera: ' + (err.message || 'Permission denied'));
            setEnrollmentStatus('error');
        }
    };

    const stopCamera = () => {
        if (stream) {
            stream.getTracks().forEach(t => t.stop());
        }
        setStream(null);
        setCameraActive(false);
    };

    const captureAndEnroll = async () => {
        const video = videoRef.current;
        const canvas = canvasRef.current;
        if (!video || !canvas) return;

        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        ctx.drawImage(video, 0, 0);
        stopCamera();

        // Convert canvas to File
        canvas.toBlob(async (blob) => {
            if (!blob) return;
            const file = new File([blob], 'webcam-capture.jpg', { type: 'image/jpeg' });
            await enrollWithFile(file);
        }, 'image/jpeg', 0.92);
    };

    // Cleanup camera on unmount
    React.useEffect(() => {
        return () => {
            if (stream) stream.getTracks().forEach(t => t.stop());
        };
    }, []);

    return (
        <Card sx={{ mt: 3 }}>
            <CardContent>
                <Typography variant="h6" gutterBottom>Face Enrollment</Typography>

                {enrollmentStatus === 'success' ? (
                    <Alert severity="success">
                        Face enrolled successfully! Quality score: {qualityScore?.toFixed(2)}
                    </Alert>
                ) : (
                    <Box>
                        <Typography variant="body2" color="textSecondary" sx={{ mb: 2 }}>
                            Enroll this member's face using a webcam or by uploading a photo.
                        </Typography>

                        {/* Webcam Preview */}
                        {cameraActive && (
                            <Box sx={{ mb: 2, position: 'relative' }}>
                                <video
                                    ref={videoRef}
                                    autoPlay
                                    playsInline
                                    muted
                                    style={{
                                        width: '100%',
                                        maxWidth: 480,
                                        borderRadius: 8,
                                        border: '2px solid',
                                        borderColor: 'primary.main',
                                    }}
                                />
                                <Box display="flex" gap={1} mt={1}>
                                    <Button
                                        variant="contained"
                                        color="primary"
                                        onClick={captureAndEnroll}
                                        disabled={enrollmentStatus === 'uploading'}
                                    >
                                        {enrollmentStatus === 'uploading' ? 'Processing...' : '📸 Capture & Enroll'}
                                    </Button>
                                    <Button variant="outlined" color="error" onClick={stopCamera}>
                                        Cancel
                                    </Button>
                                </Box>
                            </Box>
                        )}

                        {/* Action Buttons */}
                        {!cameraActive && (
                            <Box display="flex" gap={2} flexWrap="wrap">
                                <Button
                                    variant="contained"
                                    startIcon={<PhotoCamera />}
                                    onClick={startCamera}
                                    disabled={enrollmentStatus === 'uploading'}
                                >
                                    Use Webcam
                                </Button>
                                <Button
                                    variant="outlined"
                                    startIcon={<PhotoCamera />}
                                    onClick={() => fileInputRef.current?.click()}
                                    disabled={enrollmentStatus === 'uploading'}
                                >
                                    {enrollmentStatus === 'uploading' ? 'Processing...' : 'Upload Photo'}
                                </Button>
                                <input
                                    type="file"
                                    accept="image/*"
                                    onChange={handleFileUpload}
                                    ref={fileInputRef}
                                    style={{ display: 'none' }}
                                />
                            </Box>
                        )}

                        {/* Hidden canvas for webcam capture */}
                        <canvas ref={canvasRef} style={{ display: 'none' }} />

                        {enrollmentStatus === 'error' && errorMsg && (
                            <Alert severity="error" sx={{ mt: 2 }}>
                                {errorMsg}
                            </Alert>
                        )}

                        {enrollmentStatus === 'uploading' && !cameraActive && (
                            <Box display="flex" alignItems="center" gap={1} mt={2}>
                                <CircularProgress size={20} />
                                <Typography variant="body2">Processing face enrollment...</Typography>
                            </Box>
                        )}
                    </Box>
                )}
            </CardContent>
        </Card>
    );
};
